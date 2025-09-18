"""
Order Monitoring Service for COM
Watches orders for unsupported order types and uses market data to trigger them manually
"""
import asyncio
import logging
import json
import time
from datetime import datetime
from typing import Dict, Any, Optional, List, Callable
from dataclasses import dataclass

from ..core.database import Order
from ..schemas.base import OrderType, OrderSide, EventType, WSEvent
from ..core.database import get_db
from ..services.mexc_market_data import mexc_market_data
from ..adapters.manager import broker_manager
from ..ws.hub import websocket_hub

logger = logging.getLogger(__name__)

@dataclass
class MonitoredOrder:
    """Order being monitored for manual execution"""
    order_ref: str
    symbol: str
    side: OrderSide
    order_type: OrderType
    quantity: float
    price: Optional[float] = None
    stop_price: Optional[float] = None
    take_profit: Optional[float] = None
    stop_loss: Optional[float] = None
    created_at: datetime = None
    last_check: datetime = None
    status: str = "MONITORING"

    # Exit plan fields for after_fill_actions
    exit_plan: Optional[Dict[str, Any]] = None
    entry_price: Optional[float] = None
    position_size: Optional[float] = None
    strategy_id: Optional[str] = None  # For WebSocket notifications
    original_request: Optional[Any] = None  # Store original request for logging

    # Store broker order IDs for TP/SL orders to identify closing trades
    tp_broker_order_id: Optional[str] = None  # MEXC order ID for TP order
    sl_broker_order_id: Optional[str] = None  # MEXC order ID for SL order
    
    # Cache: entry broker order id (for attached SL edits)
    entry_broker_order_id: Optional[str] = None
    
    # Store stop limit order ID for TP/SL modifications
    stop_limit_order_id: Optional[int] = None  # MEXC stop limit order ID for attached TP/SL
    
    # Flag to prevent repeated SL moves
    sl_moved_to_breakeven: bool = False
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.utcnow()
        if self.last_check is None:
            self.last_check = datetime.utcnow()

class OrderMonitorService:
    """Service for monitoring orders that need manual execution"""
    
    def __init__(self):
        self.monitored_orders: Dict[str, MonitoredOrder] = {}
        self._monitoring_task: Optional[asyncio.Task] = None
        self._running = False
        
        # Callbacks for order triggers
        self._trigger_callbacks: List[Callable[[MonitoredOrder, str, float], None]] = []
        
        # Market data callbacks
        self._setup_market_data_callbacks()
        
        logger.info("Order Monitor Service initialized")
    
    def _setup_market_data_callbacks(self):
        """Setup callbacks to receive market data updates"""
        mexc_market_data.add_price_callback(self._on_price_update)
        mexc_market_data.add_orderbook_callback(self._on_orderbook_update)
        logger.info("Market data callbacks registered")
    
    async def start_monitoring(self):
        """Start the order monitoring service"""
        if self._running:
            return
        
        # Ensure market data service is connected
        if not mexc_market_data.is_connected():
            logger.info("Connecting to market data service...")
            await mexc_market_data.connect()
        
        self._running = True
        self._monitoring_task = asyncio.create_task(self._monitor_orders())
        logger.info("Order monitoring service started")
    
    async def stop_monitoring(self):
        """Stop the order monitoring service"""
        self._running = False
        
        if self._monitoring_task:
            self._monitoring_task.cancel()
            try:
                await self._monitoring_task
            except asyncio.CancelledError:
                pass
            self._monitoring_task = None
        
        logger.info("Order monitoring service stopped")
    
    async def add_order_for_monitoring(self, order: Order, original_request=None, stop_limit_order_id: Optional[int] = None) -> bool:
        """Add an order to monitoring for manual execution"""
        try:
            # Check if order type needs monitoring
            if not self._needs_monitoring(order):
                return False
            
            # Get symbol from order - try different attribute names
            symbol = "unknown"
            if hasattr(order, 'instrument') and hasattr(order.instrument, 'symbol'):
                symbol = order.instrument.symbol
            elif hasattr(order, 'symbol'):
                symbol = order.symbol

            # Parse exit plan from original request
            exit_plan = None

            # Debug logging for troubleshooting
            logger.debug(f"Processing order {order.order_ref} with symbol {symbol}")
            if original_request:
                logger.debug(f"Original request type: {type(original_request)}")
                if hasattr(original_request, 'order') and hasattr(original_request.order, 'exit_plan'):
                    logger.debug(f"Found exit plan in original request")

            if original_request and hasattr(original_request, 'order') and hasattr(original_request.order, 'exit_plan'):
                try:
                    exit_plan_obj = original_request.order.exit_plan
                    if hasattr(exit_plan_obj, 'legs'):
                        # It's an ExitPlan object with legs attribute
                        exit_plan = exit_plan_obj.legs
                        logger.info(f"Found exit plan in original request for order {order.order_ref}: {len(exit_plan)} legs")

                        logger.info(f"Found exit plan with {len(exit_plan)} legs for order {order.order_ref}")
                    else:
                        # Try to treat it as a dict
                        exit_plan = exit_plan_obj.get('legs', []) if hasattr(exit_plan_obj, 'get') else []
                except Exception as e:
                    logger.error(f"Error getting exit plan from original request for order {order.order_ref}: {e}")
                    exit_plan = None

            # Get quantity - handle both cases (with/without .value)
            quantity = order.quantity
            if hasattr(order.quantity, 'value'):
                quantity = order.quantity.value
            elif isinstance(order.quantity, (int, float)):
                quantity = float(order.quantity)

            # Create monitored order
            monitored_order = MonitoredOrder(
                order_ref=order.order_ref,
                symbol=symbol,
                side=order.side,
                order_type=order.order_type,
                quantity=quantity,
                price=order.price,
                stop_price=getattr(order, 'stop_price', None),
                take_profit=getattr(order, 'take_profit', None),
                stop_loss=getattr(order, 'stop_loss', None),
                exit_plan={'legs': exit_plan} if exit_plan else None,
                entry_price=getattr(order, 'entry_price', None),
                position_size=quantity,  # Use quantity as position size
                strategy_id=getattr(order, 'strategy_id', None),
                original_request=original_request,
                stop_limit_order_id=stop_limit_order_id
            )
            
            self.monitored_orders[order.order_ref] = monitored_order
            
            # Subscribe to market data for this symbol if not already subscribed
            if not mexc_market_data.is_connected():
                await mexc_market_data.connect()
            
            if symbol not in mexc_market_data.get_subscribed_symbols():
                await mexc_market_data.subscribe_symbol(symbol)
                logger.info(f"Subscribed to {symbol} for order monitoring")
            
            # For orders with TP/SL exit plans, always log TP/SL orders and set up monitoring
            if exit_plan:
                # exit_plan is now the legs list directly
                legs = exit_plan if isinstance(exit_plan, list) else []

                # Check if any legs have post-only execution
                has_post_only_legs = any(
                    getattr(leg, 'exec', {}).get('post_only', False) if hasattr(leg, 'get') else False
                    for leg in legs
                    if getattr(leg, 'kind', None) in ['TP', 'SL']
                )

                # Always set up monitoring if there are TP/SL legs (to log them)
                has_tp_sl_legs = any(getattr(leg, 'kind', None) in ['TP', 'SL'] for leg in legs)

                logger.info(f"📊 Exit plan analysis: {len(legs)} legs, has_post_only={has_post_only_legs}, has_tp_sl={has_tp_sl_legs}")

                if has_post_only_legs or has_tp_sl_legs:
                    logger.info(f"🚀 Setting up TP/SL monitoring for order {order.order_ref}")
                    await self._setup_post_only_tp_sl(monitored_order, legs)
                else:
                    logger.info(f"📋 No TP/SL monitoring needed for order {order.order_ref}")
            
            logger.info(f"✅ Added order {order.order_ref} to monitoring with exit plan: {exit_plan is not None}")
            logger.info(f"   Symbol: {symbol}")
            logger.info(f"   Side: {order.side}")
            logger.info(f"   Exit plan legs: {len(legs) if isinstance(exit_plan, list) else 0}")
            if exit_plan and isinstance(exit_plan, list):
                for i, leg in enumerate(exit_plan):
                    leg_kind = getattr(leg, 'kind', 'unknown')
                    leg_value = getattr(leg.trigger, 'value', 'N/A') if hasattr(leg, 'trigger') else 'N/A'
                    # Format price if it's a number, otherwise use as-is
                    if isinstance(leg_value, (int, float)):
                        price_str = f"${leg_value:,.2f}"
                    else:
                        price_str = f"${leg_value}"
                    logger.info(f"     Leg {i+1}: {leg_kind} at {price_str}")
            logger.info(f"   Total monitored orders: {len(self.monitored_orders)}")
            return True
            
        except Exception as e:
            logger.error(f"Error adding order to monitoring: {e}")
            return False
    
    def remove_order_from_monitoring(self, order_ref: str):
        """Remove an order from monitoring"""
        if order_ref in self.monitored_orders:
            del self.monitored_orders[order_ref]
            logger.info(f"Removed order {order_ref} from monitoring")
    
    def _needs_monitoring(self, order: Order) -> bool:
        """Check if an order needs monitoring for manual execution"""
        # Monitor orders that the broker doesn't support natively
        if order.order_type in [OrderType.STOP, OrderType.STOP_LIMIT]:
            return True

        # Monitor orders with TP/SL that need manual execution
        if hasattr(order, 'take_profit') and order.take_profit:
            return True

        if hasattr(order, 'stop_loss') and order.stop_loss:
            return True

        # Also monitor orders with exit plans (to log TP/SL orders)
        # This ensures we always set up monitoring for orders with exit plans
        # even if the broker handles them, so we can log the TP/SL orders
        return True  # For now, always try monitoring to see the debug output
    
    def _on_price_update(self, symbol: str, market_data):
        """Handle price updates from market data service"""
        try:
            # Check all monitored orders for this symbol
            for order_ref, monitored_order in self.monitored_orders.items():
                if monitored_order.symbol == symbol:
                    # Schedule the async check in the event loop
                    try:
                        loop = asyncio.get_event_loop()
                        if loop.is_running():
                            asyncio.create_task(self._check_order_triggers(monitored_order, market_data))
                        else:
                            loop.run_until_complete(self._check_order_triggers(monitored_order, market_data))
                    except RuntimeError:
                        # No event loop running, create a new one
                        asyncio.run(self._check_order_triggers(monitored_order, market_data))
        except Exception as e:
            logger.error(f"Error handling price update for {symbol}: {e}")
    
    def _on_orderbook_update(self, symbol: str, orderbook):
        """Handle order book updates from market data service"""
        try:
            # Check all monitored orders for this symbol
            for order_ref, monitored_order in self.monitored_orders.items():
                if monitored_order.symbol == symbol:
                    # Schedule the async check in the event loop
                    try:
                        loop = asyncio.get_event_loop()
                        if loop.is_running():
                            asyncio.create_task(self._check_order_triggers(monitored_order, orderbook))
                        else:
                            loop.run_until_complete(self._check_order_triggers(monitored_order, orderbook))
                    except RuntimeError:
                        # No event loop running, create a new one
                        asyncio.run(self._check_order_triggers(monitored_order, orderbook))
        except Exception as e:
            logger.error(f"Error handling orderbook update for {symbol}: {e}")
    
    async def _check_order_triggers(self, monitored_order: MonitoredOrder, market_data):
        """Check if an order should be triggered based on market data"""
        try:
            current_price = market_data.last_price if hasattr(market_data, 'last_price') else None
            best_bid = market_data.bid if hasattr(market_data, 'bid') else None
            best_ask = market_data.ask if hasattr(market_data, 'ask') else None
            
            if not current_price:
                logger.debug(f"No current price for {monitored_order.order_ref}")
                return
            
            logger.debug(f"🔍 Checking triggers for {monitored_order.order_ref}: price=${current_price:,.2f}, bid=${best_bid:,.2f}, ask=${best_ask:,.2f}")
            
            # Update last check time
            monitored_order.last_check = datetime.utcnow()
            
            # Check different trigger conditions
            await self._check_stop_triggers(monitored_order, current_price, best_bid, best_ask)
            await self._check_tp_sl_triggers(monitored_order, current_price, best_bid, best_ask)
            
        except Exception as e:
            logger.error(f"Error checking triggers for order {monitored_order.order_ref}: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
    
    async def _check_stop_triggers(self, monitored_order: MonitoredOrder, current_price: float, best_bid: float, best_ask: float):
        """Check if stop orders should be triggered"""
        try:
            if monitored_order.order_type == OrderType.STOP and monitored_order.stop_price:
                should_trigger = False
                trigger_price = None
                
                if monitored_order.side == OrderSide.BUY:
                    # Buy stop: trigger when price goes above stop price
                    if current_price >= monitored_order.stop_price:
                        should_trigger = True
                        trigger_price = best_ask  # Use ask price for buy
                else:
                    # Sell stop: trigger when price goes below stop price
                    if current_price <= monitored_order.stop_price:
                        should_trigger = True
                        trigger_price = best_bid  # Use bid price for sell
                
                if should_trigger and trigger_price:
                    await self._execute_stop_order(monitored_order, trigger_price)
                    
        except Exception as e:
            logger.error(f"Error checking stop triggers: {e}")
    
    async def _check_tp_sl_triggers(self, monitored_order: MonitoredOrder, current_price: float, best_bid: float, best_ask: float):
        """Check TP/SL order status instead of price triggers"""
        try:
            if not monitored_order.exit_plan:
                return
            
            logger.debug(f"🔍 Checking TP/SL order status for {monitored_order.order_ref}")
            
            # Check TP order status if we have broker order IDs
            if monitored_order.tp_broker_order_id:
                await self._check_tp_order_status(monitored_order, current_price, best_bid, best_ask)
            
            # Check SL order status if we have broker order IDs  
            if monitored_order.sl_broker_order_id:
                await self._check_sl_order_status(monitored_order, current_price, best_bid, best_ask)
                
        except Exception as e:
            logger.error(f"Error checking TP/SL triggers: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
    
    async def _check_tp_order_status(self, monitored_order: MonitoredOrder, current_price: float, best_bid: float, best_ask: float):
        """Check if TP order is filled or cancelled"""
        try:
            if not monitored_order.tp_broker_order_id:
                return
                
            # Get broker connection
            await broker_manager.ensure_broker_connected("mexc")
            broker = broker_manager.get_adapter("mexc")
            
            if not broker:
                return
                
            # Check TP order status
            order_status = await broker.get_order(monitored_order.tp_broker_order_id)
            
            if not order_status or not order_status.get('success'):
                logger.warning(f"Could not get TP order status for {monitored_order.tp_broker_order_id}")
                return
                
            order_data = order_status.get('data', {})
            status = order_data.get('state', '').upper()
            
            logger.debug(f"🔍 TP order {monitored_order.tp_broker_order_id} status: {status}")
            
            if status == 'FILLED':
                logger.info(f"✅ TP order FILLED: {monitored_order.tp_broker_order_id}")
                # Execute after_fill_actions
                await self._execute_tp_fill_actions(monitored_order, current_price)
                
            elif status == 'CANCELLED':
                logger.info(f"🔄 TP order CANCELLED (crossed books): {monitored_order.tp_broker_order_id}")
                # Execute as market order
                await self._execute_tp_as_market(monitored_order, current_price, best_bid, best_ask)
                
        except Exception as e:
            logger.error(f"Error checking TP order status: {e}")
    
    async def _check_sl_order_status(self, monitored_order: MonitoredOrder, current_price: float, best_bid: float, best_ask: float):
        """Check if SL order is filled"""
        try:
            if not monitored_order.sl_broker_order_id:
                return
                
            # Get broker connection
            await broker_manager.ensure_broker_connected("mexc")
            broker = broker_manager.get_adapter("mexc")
            
            if not broker:
                return
                
            # Check SL order status
            order_status = await broker.get_order(monitored_order.sl_broker_order_id)
            
            if not order_status or not order_status.get('success'):
                logger.warning(f"Could not get SL order status for {monitored_order.sl_broker_order_id}")
                return
                
            order_data = order_status.get('data', {})
            status = order_data.get('state', '').upper()
            
            logger.debug(f"🔍 SL order {monitored_order.sl_broker_order_id} status: {status}")
            
            if status == 'FILLED':
                logger.info(f"✅ SL order FILLED: {monitored_order.sl_broker_order_id}")
                # SL filled - position closed
                
        except Exception as e:
            logger.error(f"Error checking SL order status: {e}")
    
    async def _execute_tp_fill_actions(self, monitored_order: MonitoredOrder, fill_price: float):
        """Execute after_fill_actions when TP order fills"""
        try:
            if not monitored_order.exit_plan:
                return
                
            # Find the TP leg that filled
            for leg in monitored_order.exit_plan.get('legs', []):
                if leg.get('kind') == 'TP':
                    after_fill_actions = leg.get('after_fill_actions', [])
                    if after_fill_actions:
                        logger.info(f"🎯 Executing {len(after_fill_actions)} after_fill_actions for TP fill")
                        await self._execute_after_fill_actions_for_tp(monitored_order, after_fill_actions, fill_price)
                        break
                        
        except Exception as e:
            logger.error(f"Error executing TP fill actions: {e}")
    
    async def _execute_tp_as_market(self, monitored_order: MonitoredOrder, current_price: float, best_bid: float, best_ask: float):
        """Execute TP as market order when post-only was cancelled"""
        try:
            logger.info(f"🔄 Executing TP as market order for {monitored_order.order_ref}")
            
            # Get broker connection
            await broker_manager.ensure_broker_connected("mexc")
            broker = broker_manager.get_adapter("mexc")
            
            if not broker:
                logger.error("❌ No broker connection available")
                return
                
            # Create market order for TP
            from ..schemas.orders import CreateOrderRequest, Instrument, Quantity, OrderFlags, Routing, Leverage
            
            # Determine side for TP (opposite of entry)
            tp_side = "BUY" if monitored_order.side == OrderSide.SELL else "SELL"
            
            # Use best available price
            tp_price = best_ask if tp_side == "BUY" else best_bid
            
            tp_order = CreateOrderRequest(
                idempotency_key=f"tp_market_{monitored_order.order_ref}_{int(time.time())}",
                environment={"sandbox": True},
                source={
                    "strategy_id": monitored_order.strategy_id or "unknown",
                    "instance_id": "tp_market_execution",
                    "owner": "system"
                },
                order={
                    "instrument": Instrument(
                        **{"class": "crypto_perp"},
                        symbol=monitored_order.symbol
                    ),
                    "side": tp_side,
                    "quantity": Quantity(
                        type="contracts",
                        value=monitored_order.quantity
                    ),
                    "order_type": "MARKET",
                    "time_in_force": "IOC",
                    "flags": OrderFlags(
                        post_only=False,
                        reduce_only=True,
                        hidden=False,
                        iceberg={},
                        allow_partial_fills=True
                    ),
                    "routing": Routing(mode="DIRECT", direct={"broker": "mexc"}),
                    "leverage": Leverage(enabled=False, leverage=None)
                }
            )
            
            # Place market TP order
            result = await broker.place_order(tp_order)
            
            if result.get('success'):
                logger.info(f"✅ TP market order placed successfully: {result.get('broker_order_id')}")
                # Execute after_fill_actions
                await self._execute_tp_fill_actions(monitored_order, tp_price)
            else:
                logger.error(f"❌ Failed to place TP market order: {result.get('error')}")
                
        except Exception as e:
            logger.error(f"Error executing TP as market: {e}")
    
    async def _execute_stop_order(self, monitored_order: MonitoredOrder, trigger_price: float):
        """Execute a stop order manually"""
        try:
            logger.info(f"Executing stop order {monitored_order.order_ref} at {trigger_price}")
            
            # Get broker adapter
            broker_name = "mexc"  # For now, hardcoded to MEXC
            await broker_manager.ensure_broker_connected(broker_name)
            broker = broker_manager.get_adapter(broker_name)
            
            if not broker:
                logger.error(f"Broker {broker_name} not available")
                return
            
            # Create market order to execute the stop
            # This would need to be implemented based on your order creation logic
            # For now, just log the trigger
            
            # Trigger callbacks
            for callback in self._trigger_callbacks:
                try:
                    callback(monitored_order, "STOP_TRIGGERED", trigger_price)
                except Exception as e:
                    logger.error(f"Error in trigger callback: {e}")
            
            # Remove from monitoring
            self.remove_order_from_monitoring(monitored_order.order_ref)
            
        except Exception as e:
            logger.error(f"Error executing stop order: {e}")
    
    async def _execute_take_profit(self, monitored_order: MonitoredOrder, trigger_price: float):
        """Execute a take profit order manually"""
        try:
            logger.info(f"Executing take profit for order {monitored_order.order_ref} at {trigger_price}")
            
            # Similar logic to stop order execution
            # This would create a market order to close the position
            
            # Trigger callbacks
            for callback in self._trigger_callbacks:
                try:
                    callback(monitored_order, "TAKE_PROFIT_TRIGGERED", trigger_price)
                except Exception as e:
                    logger.error(f"Error in trigger callback: {e}")
            
            # Remove from monitoring
            self.remove_order_from_monitoring(monitored_order.order_ref)
            
        except Exception as e:
            logger.error(f"Error executing take profit: {e}")
    
    async def _execute_stop_loss(self, monitored_order: MonitoredOrder, trigger_price: float):
        """Execute a stop loss order manually with smart orderbook placement"""
        try:
            logger.info(f"Executing stop loss for order {monitored_order.order_ref} at {trigger_price}")
            
            # Get broker adapter
            broker_name = "mexc"
            await broker_manager.ensure_broker_connected(broker_name)
            broker = broker_manager.get_adapter(broker_name)
            
            if not broker:
                logger.error(f"Broker {broker_name} not available")
                return
            
            # For post-only TP/SL orders, we need to:
            # 1. Cancel any existing TP orders
            # 2. Place SL at optimal price in orderbook
            
            if hasattr(monitored_order, 'tp_broker_order_id') and monitored_order.tp_broker_order_id:
                try:
                    # Cancel the TP order first
                    await broker.cancel_order(monitored_order.tp_broker_order_id)
                    logger.info(f"Cancelled TP order {monitored_order.tp_broker_order_id}")
                except Exception as e:
                    logger.warning(f"Failed to cancel TP order: {e}")
            
            # Get current orderbook to find optimal SL placement
            orderbook = await mexc_market_data.get_orderbook(monitored_order.symbol)
            if not orderbook:
                logger.error(f"No orderbook data for {monitored_order.symbol}")
                return
            
            # Find optimal SL price based on orderbook depth
            optimal_sl_price = await self._find_optimal_sl_price(
                monitored_order, orderbook, trigger_price
            )
            
            # Get SL leg configuration for post-only check
            self.current_sl_leg = None
            if monitored_order.exit_plan and 'legs' in monitored_order.exit_plan:
                for leg in monitored_order.exit_plan['legs']:
                    if leg.get('kind') == 'SL':
                        self.current_sl_leg = leg
                        break
            
            # Create and place the SL order
            sl_order_result = await self._place_sl_order(
                monitored_order, optimal_sl_price, broker, self.current_sl_leg
            )
            
            if sl_order_result["success"]:
                # Store the broker order ID for the SL order
                monitored_order.sl_broker_order_id = sl_order_result.get("broker_order_id", "")
                logger.info(f"✅ Placed SL order at optimal price: {optimal_sl_price}, ID: {monitored_order.sl_broker_order_id}")

                # Trigger callbacks
                for callback in self._trigger_callbacks:
                    try:
                        callback(monitored_order, "STOP_LOSS_TRIGGERED", optimal_sl_price)
                    except Exception as e:
                        logger.error(f"Error in trigger callback: {e}")
            else:
                logger.error(f"❌ Failed to place SL order: {sl_order_result['error']}")
            
            # Remove from monitoring
            self.remove_order_from_monitoring(monitored_order.order_ref)
            
        except Exception as e:
            logger.error(f"Error executing stop loss: {e}")
    
    async def _find_optimal_sl_price(self, monitored_order: MonitoredOrder, orderbook: dict, trigger_price: float) -> float:
        """Find optimal SL price based on orderbook depth"""
        try:
            # Get orderbook data
            bids = orderbook.get('bids', [])
            asks = orderbook.get('asks', [])
            
            if not bids or not asks:
                logger.warning("Insufficient orderbook data, using trigger price")
                return trigger_price
            
            # For SL orders, we want to place at the best available price
            # that will execute quickly to minimize slippage
            
            if monitored_order.side == OrderSide.BUY:
                # For long positions, SL is a sell order
                # Place at the best bid or slightly below for quick execution
                best_bid = float(bids[0][0]) if bids else trigger_price
                optimal_price = best_bid * 0.999  # Slightly below best bid for quick fill
            else:
                # For short positions, SL is a buy order  
                # Place at the best ask or slightly above for quick execution
                best_ask = float(asks[0][0]) if asks else trigger_price
                optimal_price = best_ask * 1.001  # Slightly above best ask for quick fill
            
            # Ensure price is not worse than trigger price
            if monitored_order.side == OrderSide.BUY:
                optimal_price = max(optimal_price, trigger_price)
            else:
                optimal_price = min(optimal_price, trigger_price)
            
            logger.info(f"Optimal SL price: {optimal_price} (trigger: {trigger_price}, best_bid: {bids[0][0] if bids else 'N/A'}, best_ask: {asks[0][0] if asks else 'N/A'})")
            return optimal_price
            
        except Exception as e:
            logger.error(f"Error finding optimal SL price: {e}")
            return trigger_price
    
    async def _place_sl_order(self, monitored_order: MonitoredOrder, price: float, broker, sl_leg: dict = None) -> dict:
        """Place a stop loss order at the specified price"""
        try:
            from ..schemas.orders import OrderRequest
            from ..schemas.base import Instrument, Quantity, Flags, Routing, Leverage
            
            # Check if SL should be post-only from the leg configuration
            sl_post_only = False
            if self.current_sl_leg and 'exec' in self.current_sl_leg:
                exec_config = self.current_sl_leg['exec']
                if isinstance(exec_config, dict) and exec_config.get('post_only'):
                    sl_post_only = True
                elif hasattr(exec_config, 'post_only') and exec_config.post_only:
                    sl_post_only = True
            
            # Determine order type and execution strategy
            if sl_post_only:
                # Post-only SL: use LIMIT order at optimal price
                order_type = "LIMIT"
                time_in_force = "GTC"
                execution_price = price
            else:
                # Regular SL: use MARKET order for quick execution
                order_type = "MARKET"
                time_in_force = "IOC"
                execution_price = None  # Market orders don't need price
            
            # Create SL order
            sl_order = OrderRequest(
                instrument=Instrument(
                    class_="crypto_perp",
                    symbol=monitored_order.symbol
                ),
                side="SELL" if monitored_order.side == OrderSide.BUY else "BUY",
                quantity=Quantity(
                    type="contracts",
                    value=monitored_order.quantity
                ),
                order_type=order_type,
                price=execution_price,
                time_in_force=time_in_force,
                flags=Flags(
                    post_only=sl_post_only,
                    reduce_only=True,
                    hidden=False,
                    iceberg={},
                    allow_partial_fills=True
                ),
                routing=Routing(mode="DIRECT", direct={"broker": "mexc"}),
                leverage=Leverage(enabled=False, leverage=None)
            )
            
            logger.info(f"Placing SL order: {order_type}, post_only={sl_post_only}, price={execution_price}")
            
            # Place order with broker
            result = await broker.place_order(sl_order)
            
            # Log SL order to CSV if successful
            if result.get("success"):
                try:
                    from .orders import order_service
                    broker_order_id = result.get("broker_order_id", "")
                    await order_service._log_tp_sl_order(
                        monitored_order.original_request,  # We need to pass the original request
                        broker_order_id,
                        "SL",
                        sl_order.side,
                        monitored_order.quantity,
                        execution_price or 0.0,
                        monitored_order.order_ref
                    )
                    # Store the broker order ID for later identification
                    monitored_order.sl_broker_order_id = broker_order_id
                    logger.info(f"📝 Stored SL broker order ID: {broker_order_id}")
                except Exception as e:
                    logger.error(f"Error logging SL order: {e}")
            
            return result
            
        except Exception as e:
            logger.error(f"Error placing SL order: {e}")
            return {"success": False, "error": str(e)}
    
    async def _setup_post_only_tp_sl(self, monitored_order: MonitoredOrder, legs):
        """Setup post-only TP/SL orders - place TP as post-only, monitor for SL trigger"""
        try:
            logger.info(f"Setting up post-only TP/SL for order {monitored_order.order_ref}")
            
            # Check if this order already has proper exit plan handling
            # If the order has after_fill_actions, it means it was handled by the orders service
            # and we should not create trigger orders
            has_after_fill_actions = False
            for leg in legs:
                if hasattr(leg, 'after_fill_actions') and leg.after_fill_actions:
                    has_after_fill_actions = True
                    break
            
            if has_after_fill_actions:
                logger.info(f"🔍 Order {monitored_order.order_ref} already has proper exit plan handling, skipping trigger order creation")
                return
            
            # Get broker adapter
            broker_name = "mexc"
            await broker_manager.ensure_broker_connected(broker_name)
            broker = broker_manager.get_adapter(broker_name)
            
            if not broker:
                logger.error(f"Broker {broker_name} not available")
                return
            
            # Find TP and SL legs and check their configurations
            self.current_tp_leg = None
            self.current_sl_leg = None
            tp_post_only = False
            sl_post_only = False
            
            for leg in legs:
                logger.info(f"🔧 Processing leg: {leg}, type: {type(leg)}")
                leg_kind = None
                exec_config = {}

                # Handle both dict and ExitLeg object formats
                if hasattr(leg, 'kind'):
                    # ExitLeg object
                    leg_kind = leg.kind
                    logger.info(f"🔧 Leg kind (object): {leg_kind}")
                    if hasattr(leg, 'exec') and leg.exec:
                        exec_config = leg.exec
                        logger.info(f"🔧 Exec config (object): {exec_config}")
                        post_only_value = exec_config.post_only if hasattr(exec_config, 'post_only') else False
                        logger.info(f"🔧 Post-only value (object): {post_only_value}")
                else:
                    # Dict format
                    leg_kind = leg.get('kind')
                    logger.info(f"🔧 Leg kind (dict): {leg_kind}")
                    exec_config = leg.get('exec', {})
                    logger.info(f"🔧 Exec config (dict): {exec_config}")
                    post_only_value = exec_config.get('post_only', False) if isinstance(exec_config, dict) else False
                    logger.info(f"🔧 Post-only value (dict): {post_only_value}")

                if post_only_value:
                    if leg_kind == 'TP':
                        tp_post_only = True
                        logger.info(f"🔧 Set TP as post-only")
                    elif leg_kind == 'SL':
                        sl_post_only = True
                        logger.info(f"🔧 Set SL as post-only")

                if leg_kind == 'TP':
                    self.current_tp_leg = leg
                elif leg_kind == 'SL':
                    self.current_sl_leg = leg
            
            # Store order reference for use in nested functions
            self.current_order = monitored_order

            # Store legs for use in nested functions
            # (already set above, no need to reassign)

            # Place TP order (post-only or regular trigger order)
            if self.current_tp_leg:
                logger.info(f"🔧 TP LEG: {self.current_tp_leg}, POST_ONLY: {tp_post_only}")
                logger.info(f"🔧 TP LEG TYPE: {type(self.current_tp_leg)}")
                if hasattr(self.current_tp_leg, 'trigger'):
                    logger.info(f"🔧 TP LEG TRIGGER: {self.current_tp_leg.trigger}")
                    if hasattr(self.current_tp_leg.trigger, 'value'):
                        logger.info(f"🔧 TP LEG TRIGGER VALUE: {self.current_tp_leg.trigger.value}")
                
                tp_placed_successfully = False
                if tp_post_only:
                    # Place as post-only limit order
                    logger.info(f"📝 Placing post-only TP order...")
                    tp_order_result = await self._place_post_only_tp(monitored_order, self.current_tp_leg, broker)
                    if tp_order_result["success"]:
                        monitored_order.tp_broker_order_id = tp_order_result["broker_order_id"]
                        tp_placed_successfully = True
                        logger.info(f"✅ Placed post-only TP order: {monitored_order.tp_broker_order_id}")
                    else:
                        logger.error(f"❌ Failed to place TP order: {tp_order_result['error']}")
                else:
                    # Place as MEXC trigger order
                    logger.info(f"📝 Placing TP trigger order...")
                    tp_trigger_result = await self._place_trigger_tp(monitored_order, self.current_tp_leg, broker)
                    logger.info(f"📝 TP trigger result: {tp_trigger_result}")
                    if tp_trigger_result["success"]:
                        monitored_order.tp_broker_order_id = tp_trigger_result["trigger_id"]
                        tp_placed_successfully = True
                        logger.info(f"✅ Placed TP trigger order: {monitored_order.tp_broker_order_id}")
                    else:
                        logger.error(f"❌ Failed to place TP trigger order: {tp_trigger_result['error']}")
                
                # Log TP order ONLY if it was successfully placed on broker
                if tp_placed_successfully:
                    # Get TP price - handle both ExitLeg and dict formats
                    logger.info(f"🔧 Extracting TP price from leg...")
                    tp_price = None

                    if hasattr(self.current_tp_leg, 'trigger'):
                        logger.info(f"🔧 TP trigger object: {self.current_tp_leg.trigger}")
                        logger.info(f"🔧 TP trigger attributes: {dir(self.current_tp_leg.trigger)}")

                        # Try to get value directly
                        if hasattr(self.current_tp_leg.trigger, 'value'):
                            tp_price = self.current_tp_leg.trigger.value
                            logger.info(f"🔧 TP price extracted via trigger.value: {tp_price}")
                        elif hasattr(self.current_tp_leg.trigger, 'get') and callable(getattr(self.current_tp_leg.trigger, 'get')):
                            # For dict-like structures, get the value
                            tp_price = self.current_tp_leg.trigger.get('value')
                            logger.info(f"🔧 TP price extracted via trigger.get('value'): {tp_price}")
                        else:
                            logger.info(f"🔧 TP trigger has neither 'value' nor 'get' method")

                    # Fallback for dict format
                    if tp_price is None:
                        tp_price = self.current_tp_leg.get('trigger', {}).get('value') if hasattr(self.current_tp_leg, 'get') else None
                        logger.info(f"🔧 TP price extracted via dict fallback: {tp_price}")

                    logger.info(f"🔧 Final TP price: {tp_price} (type: {type(tp_price)})")
                    tp_side = "SELL" if monitored_order.side == OrderSide.BUY else "BUY"  # Opposite side for TP

                    try:
                        logger.info(f"📊 About to log TP order with price: {tp_price} (type: {type(tp_price)})")
                        from .orders import order_service
                        # Add TP order to position tracker
                        logger.info(f"📊 Adding TP order to position tracker...")
                        from .position_tracker import position_tracker

                        # Get position_id from the original order
                        position_id = None
                        if hasattr(self.current_order, 'parent_position_id'):
                            position_id = self.current_order.parent_position_id
                            logger.info(f"📊 Found position_id from order: {position_id}")

                        if position_id:
                            tp_order_id = position_tracker.add_order(
                                broker_order_id=monitored_order.tp_broker_order_id,
                                parent_position_id=position_id,
                                order_type="TP",
                                side=tp_side,
                                quantity=monitored_order.quantity,
                                price=tp_price,
                                strategy_id=getattr(monitored_order, 'strategy_id', None),
                                order_ref=f"{monitored_order.order_ref}_tp"
                            )
                            logger.info(f"✅ Added TP order {tp_order_id} to position tracker")
                        else:
                            logger.warning(f"⚠️ Cannot add TP order to position tracker: no position_id found")

                        await order_service._log_tp_sl_order(
                            monitored_order.original_request,
                            monitored_order.tp_broker_order_id or "",  # Use stored broker order ID
                            "TP",
                            tp_side,
                            monitored_order.quantity,
                            tp_price,
                            monitored_order.order_ref
                        )
                        logger.info(f"📊 Successfully logged TP monitoring order: {monitored_order.order_ref}_tp at {tp_price} with side {tp_side}, broker_id: {monitored_order.tp_broker_order_id or 'None'}")
                    except Exception as e:
                        logger.error(f"Error logging TP monitoring order: {e}")
                        import traceback
                        logger.error(f"Traceback: {traceback.format_exc()}")

            # Set up SL monitoring based on configuration
            if self.current_sl_leg:
                logger.info(f"🔧 SL LEG: {self.current_sl_leg}, POST_ONLY: {sl_post_only}")
                logger.info(f"🔧 SL LEG TYPE: {type(self.current_sl_leg)}")
                if hasattr(self.current_sl_leg, 'trigger'):
                    logger.info(f"🔧 SL LEG TRIGGER: {self.current_sl_leg.trigger}")
                    if hasattr(self.current_sl_leg.trigger, 'value'):
                        logger.info(f"🔧 SL LEG TRIGGER VALUE: {self.current_sl_leg.trigger.value}")
                
                sl_placed_successfully = False
                if sl_post_only:
                    # Post-only SL: place as post-only limit order
                    logger.info(f"📝 Placing post-only SL order...")
                    sl_order_result = await self._place_post_only_sl(monitored_order, self.current_sl_leg, broker)
                    if sl_order_result["success"]:
                        monitored_order.sl_broker_order_id = sl_order_result["broker_order_id"]
                        sl_placed_successfully = True
                        logger.info(f"✅ Placed post-only SL order: {monitored_order.sl_broker_order_id}")
                    else:
                        logger.error(f"❌ Failed to place SL order: {sl_order_result['error']}")
                else:
                    # Regular SL: place as MEXC trigger order
                    logger.info(f"📝 Placing SL trigger order...")
                    sl_trigger_result = await self._place_trigger_sl(monitored_order, self.current_sl_leg, broker)
                    logger.info(f"📝 SL trigger result: {sl_trigger_result}")
                    if sl_trigger_result["success"]:
                        monitored_order.sl_broker_order_id = sl_trigger_result["trigger_id"]
                        sl_placed_successfully = True
                        logger.info(f"✅ Placed SL trigger order: {monitored_order.sl_broker_order_id}")
                    else:
                        logger.error(f"❌ Failed to place SL trigger order: {sl_trigger_result['error']}")
                
                # Log SL order ONLY if it was successfully placed on broker
                if sl_placed_successfully:
                    # Get SL price - handle both ExitLeg and dict formats
                    logger.info(f"🔧 Extracting SL price from leg...")
                    sl_price = None

                    if hasattr(self.current_sl_leg, 'trigger'):
                        logger.info(f"🔧 SL trigger object: {self.current_sl_leg.trigger}")
                        logger.info(f"🔧 SL trigger attributes: {dir(self.current_sl_leg.trigger)}")

                        # Try to get value directly
                        if hasattr(self.current_sl_leg.trigger, 'value'):
                            sl_price = self.current_sl_leg.trigger.value
                            logger.info(f"🔧 SL price extracted via trigger.value: {sl_price}")
                        elif hasattr(self.current_sl_leg.trigger, 'get') and callable(getattr(self.current_sl_leg.trigger, 'get')):
                            # For dict-like structures, get the value
                            sl_price = self.current_sl_leg.trigger.get('value')
                            logger.info(f"🔧 SL price extracted via trigger.get('value'): {sl_price}")
                        else:
                            logger.info(f"🔧 SL trigger has neither 'value' nor 'get' method")

                    # Fallback for dict format
                    if sl_price is None:
                        sl_price = self.current_sl_leg.get('trigger', {}).get('value') if hasattr(self.current_sl_leg, 'get') else None
                        logger.info(f"🔧 SL price extracted via dict fallback: {sl_price}")

                    logger.info(f"🔧 Final SL price: {sl_price} (type: {type(sl_price)})")
                    monitored_order.stop_loss = sl_price

                    # Log SL order immediately (similar to TP orders)
                    try:
                        logger.info(f"📊 About to log SL order with price: {sl_price} (type: {type(sl_price)})")
                        from .orders import order_service
                        sl_side = "BUY" if monitored_order.side == OrderSide.BUY else "SELL"  # Opposite side for SL

                        # Add SL order to position tracker
                        logger.info(f"📊 Adding SL order to position tracker...")
                        from .position_tracker import position_tracker

                        # Get position_id from the original order
                        position_id = None
                        if hasattr(self.current_order, 'parent_position_id'):
                            position_id = self.current_order.parent_position_id
                            logger.info(f"📊 Found position_id from order: {position_id}")

                        if position_id:
                            sl_order_id = position_tracker.add_order(
                                broker_order_id=monitored_order.sl_broker_order_id,
                                parent_position_id=position_id,
                                order_type="SL",
                                side=sl_side,
                                quantity=monitored_order.quantity,
                                price=sl_price,
                                strategy_id=getattr(monitored_order, 'strategy_id', None),
                                order_ref=f"{monitored_order.order_ref}_sl"
                            )
                            logger.info(f"✅ Added SL order {sl_order_id} to position tracker")
                        else:
                            logger.warning(f"⚠️ Cannot add SL order to position tracker: no position_id found")

                        # Log the SL order as OPEN status
                        await order_service._log_tp_sl_order(
                            monitored_order.original_request,
                            monitored_order.sl_broker_order_id or "",  # Use stored broker order ID
                            "SL",
                            sl_side,
                            monitored_order.quantity,
                            sl_price,
                            monitored_order.order_ref
                        )
                        logger.info(f"📊 Successfully logged SL monitoring order: {monitored_order.order_ref}_sl at {sl_price} with side {sl_side}, broker_id: {monitored_order.sl_broker_order_id or 'None'}")
                    except Exception as e:
                        logger.error(f"Error logging SL monitoring order: {e}")
                        import traceback
                        logger.error(f"Traceback: {traceback.format_exc()}")
            
        except Exception as e:
            logger.error(f"Error setting up post-only TP/SL: {e}")
    
    async def _place_post_only_tp(self, monitored_order: MonitoredOrder, tp_leg, broker) -> dict:
        """Place a post-only take profit order"""
        try:
            from ..schemas.orders import OrderRequest
            from ..schemas.base import Instrument, Quantity, Flags, Routing, Leverage

            # Extract TP price from self.current_tp_leg
            if hasattr(self.current_tp_leg, 'trigger') and hasattr(self.current_tp_leg.trigger, 'value'):
                tp_order_price = self.current_tp_leg.trigger.value
            elif hasattr(self.current_tp_leg, 'trigger') and hasattr(self.current_tp_leg.trigger, 'price_type'):
                tp_order_price = self.current_tp_leg.trigger.value if hasattr(self.current_tp_leg.trigger, 'value') else None
            else:
                # Fallback for dict format
                tp_order_price = self.current_tp_leg.get('trigger', {}).get('value') if hasattr(self.current_tp_leg, 'get') else None

            if tp_order_price is None:
                return {"success": False, "error": "Could not extract TP price from leg"}

            # Create post-only TP order
            tp_order = OrderRequest(
                instrument=Instrument(
                    class_="crypto_perp",
                    symbol=monitored_order.symbol
                ),
                side="SELL" if monitored_order.side == OrderSide.BUY else "BUY",
                quantity=Quantity(
                    type="contracts",
                    value=monitored_order.quantity
                ),
                order_type="LIMIT",
                price=tp_order_price,
                time_in_force="GTC",
                flags=Flags(
                    post_only=True,  # This is the key - post-only TP
                    reduce_only=True,
                    hidden=False,
                    iceberg={},
                    allow_partial_fills=True
                ),
                routing=Routing(mode="DIRECT", direct={"broker": "mexc"}),
                leverage=Leverage(enabled=False, leverage=None)
            )
            
            # Place order with broker
            result = await broker.place_order(tp_order)

            # Log TP order to CSV if successful
            if result.get("success"):
                try:
                    from .orders import order_service
                    broker_order_id = result.get("broker_order_id", "")
                    await order_service._log_tp_sl_order(
                        monitored_order.original_request,
                        broker_order_id,
                        "TP",
                        tp_order.side,
                        monitored_order.quantity,
                        tp_order_price,
                        monitored_order.order_ref
                    )
                    # Store the broker order ID for later identification
                    monitored_order.tp_broker_order_id = broker_order_id
                    logger.info(f"📝 Stored TP broker order ID: {broker_order_id}")
                except Exception as e:
                    logger.error(f"Error logging TP order: {e}")

            return result
            
        except Exception as e:
            logger.error(f"Error placing post-only TP order: {e}")
            return {"success": False, "error": str(e)}

    async def _place_trigger_tp(self, monitored_order: MonitoredOrder, tp_leg, broker) -> dict:
        """Place a TP trigger order with MEXC"""
        try:
            logger.info(f"🎯 Starting TP trigger order placement for {monitored_order.symbol}")

            # Get TP price
            tp_price = None
            if hasattr(self.current_tp_leg, 'trigger'):
                if hasattr(self.current_tp_leg.trigger, 'value'):
                    tp_price = self.current_tp_leg.trigger.value
                elif hasattr(self.current_tp_leg.trigger, 'get') and callable(getattr(self.current_tp_leg.trigger, 'get')):
                    tp_price = self.current_tp_leg.trigger.get('value')
            if tp_price is None and hasattr(self.current_tp_leg, 'get'):
                tp_price = self.current_tp_leg.get('trigger', {}).get('value')

            logger.info(f"🎯 TP price extracted: {tp_price}")

            if tp_price is None:
                return {"success": False, "error": "Could not extract TP price from leg"}

            # Create trigger order request
            from mexcpy.mexcTypes import TriggerOrderRequest, TriggerType, TriggerPriceType

            # Determine the correct side for closing the position
            # For TP: we want to close the position, so opposite of entry side
            if monitored_order.side == OrderSide.BUY:
                close_side = 4  # SELL to close BUY position
            else:
                close_side = 1  # BUY to close SELL position

            trigger_request = TriggerOrderRequest(
                symbol=monitored_order.symbol,
                side=close_side,  # Close position side
                triggerType=TriggerType.GreaterThanOrEqual,  # TP triggers when price >= target
                triggerPrice=tp_price,
                price=tp_price,  # Execute at trigger price
                vol=monitored_order.quantity,
                openType=1,  # Isolated margin
                leverage=monitored_order.position_size if hasattr(monitored_order, 'position_size') else 1,
                executeCycle=1,  # Execute once
                orderType=1,  # Market order when triggered
                trend=1  # Long position trend
            )

            # Place trigger order
            logger.info(f"🎯 Placing TP trigger order with broker: {trigger_request}")
            result = await broker.api.create_trigger_order(trigger_request)
            logger.info(f"🎯 TP trigger order result: success={result.success}, data={result.data}")

            if result.success and result.data:
                # result.data is the trigger order ID (integer or string)
                trigger_id = str(result.data)
                logger.info(f"🎯 TP trigger order placed successfully with ID: {trigger_id}")
                return {
                    "success": True,
                    "trigger_id": trigger_id,
                    "message": f"TP trigger order placed at {tp_price}"
                }
            else:
                logger.error(f"🎯 TP trigger order failed: {result}")
                return {"success": False, "error": f"Failed to place TP trigger order: {result}"}

        except Exception as e:
            logger.error(f"Error placing TP trigger order: {e}")
            return {"success": False, "error": str(e)}

    async def _place_trigger_sl(self, monitored_order: MonitoredOrder, sl_leg, broker) -> dict:
        """Place an SL trigger order with MEXC"""
        try:
            logger.info(f"🎯 Starting SL trigger order placement for {monitored_order.symbol}")

            # Get SL price
            sl_price = None
            if hasattr(self.current_sl_leg, 'trigger'):
                if hasattr(self.current_sl_leg.trigger, 'value'):
                    sl_price = self.current_sl_leg.trigger.value
                elif hasattr(self.current_sl_leg.trigger, 'get') and callable(getattr(self.current_sl_leg.trigger, 'get')):
                    sl_price = self.current_sl_leg.trigger.get('value')
            if sl_price is None and hasattr(self.current_sl_leg, 'get'):
                sl_price = self.current_sl_leg.get('trigger', {}).get('value')

            logger.info(f"🎯 SL price extracted: {sl_price}")

            if sl_price is None:
                return {"success": False, "error": "Could not extract SL price from leg"}

            # Create trigger order request
            from mexcpy.mexcTypes import TriggerOrderRequest, TriggerType, TriggerPriceType

            # Determine the correct side for closing the position
            # For SL: we want to close the position, so opposite of entry side
            if monitored_order.side == OrderSide.BUY:
                close_side = 4  # SELL to close BUY position
            else:
                close_side = 1  # BUY to close SELL position

            trigger_request = TriggerOrderRequest(
                symbol=monitored_order.symbol,
                side=close_side,  # Close position side
                triggerType=TriggerType.LessThanOrEqual,  # SL triggers when price <= target
                triggerPrice=sl_price,
                price=sl_price,  # Execute at trigger price (market order)
                vol=monitored_order.quantity,
                openType=1,  # Isolated margin
                leverage=monitored_order.position_size if hasattr(monitored_order, 'position_size') else 1,
                executeCycle=1,  # Execute once
                orderType=1,  # Market order when triggered
                trend=1  # Long position trend
            )

            # Place trigger order
            logger.info(f"🎯 Placing SL trigger order with broker: {trigger_request}")
            result = await broker.api.create_trigger_order(trigger_request)
            logger.info(f"🎯 SL trigger order result: success={result.success}, data={result.data}")

            if result.success and result.data:
                # result.data is the trigger order ID (integer or string)
                trigger_id = str(result.data)
                logger.info(f"🎯 SL trigger order placed successfully with ID: {trigger_id}")
                return {
                    "success": True,
                    "trigger_id": trigger_id,
                    "message": f"SL trigger order placed at {sl_price}"
                }
            else:
                logger.error(f"🎯 SL trigger order failed: {result}")
                return {"success": False, "error": f"Failed to place SL trigger order: {result}"}

        except Exception as e:
            logger.error(f"Error placing SL trigger order: {e}")
            return {"success": False, "error": str(e)}

    async def _place_post_only_sl(self, monitored_order: MonitoredOrder, sl_leg, broker) -> dict:
        """Place a post-only stop loss order"""
        try:
            from ..schemas.orders import OrderRequest
            from ..schemas.base import Instrument, Quantity, Flags, Routing, Leverage

            # Extract SL price from self.current_sl_leg
            if hasattr(self.current_sl_leg, 'trigger') and hasattr(self.current_sl_leg.trigger, 'value'):
                sl_order_price = self.current_sl_leg.trigger.value
            elif hasattr(self.current_sl_leg, 'trigger') and hasattr(self.current_sl_leg.trigger, 'price_type'):
                sl_order_price = self.current_sl_leg.trigger.value if hasattr(self.current_sl_leg.trigger, 'value') else None
            else:
                sl_order_price = self.current_sl_leg.get('trigger', {}).get('value') if hasattr(self.current_sl_leg, 'get') else None

            if sl_order_price is None:
                return {"success": False, "error": "Could not extract SL price from leg"}

            # Create post-only SL order
            sl_order = OrderRequest(
                instrument=Instrument(
                    class_="crypto_perp",
                    symbol=monitored_order.symbol
                ),
                side="SELL" if monitored_order.side == OrderSide.BUY else "BUY",
                quantity=Quantity(
                    type="contracts",
                    value=monitored_order.quantity
                ),
                order_type="LIMIT",
                price=sl_order_price,
                time_in_force="GTC",
                flags=Flags(
                    post_only=True,  # This is the key - post-only SL
                    reduce_only=True,
                    hidden=False,
                    iceberg={},
                    allow_partial_fills=True
                ),
                routing=Routing(mode="DIRECT", direct={"broker": "mexc"}),
                leverage=Leverage(enabled=False, leverage=None)
            )

            # Place order with broker
            result = await broker.place_order(sl_order)
            return result

        except Exception as e:
            logger.error(f"Error placing post-only SL order: {e}")
            return {"success": False, "error": str(e)}
    
    async def cleanup_position_orders(self, order_ref: str, reason: str = "POSITION_CLOSED"):
        """Cancel all orders associated with a position when it's closed"""
        try:
            logger.info(f"🧹 Cleaning up orders for position {order_ref} (reason: {reason})")
            
            # Get broker adapter
            broker_name = "mexc"
            await broker_manager.ensure_broker_connected(broker_name)
            broker = broker_manager.get_adapter(broker_name)
            
            if not broker:
                logger.error(f"Broker {broker_name} not available for cleanup")
                return
            
            # Get the monitored order
            monitored_order = self.monitored_orders.get(order_ref)
            if not monitored_order:
                logger.warning(f"No monitored order found for {order_ref}")
                return
            
            cancelled_orders = []
            
            # Update order statuses in logs based on close reason
            from .orders import order_service

            if reason == "TP_FILLED":
                # TP was filled, cancel SL and update statuses
                await order_service.update_order_status(f"{order_ref}_tp", "FILLED")
                if hasattr(monitored_order, 'sl_order_id') and monitored_order.sl_order_id:
                    await order_service.update_order_status(f"{order_ref}_sl", "CANCELLED")
                    await broker.cancel_order(monitored_order.sl_order_id)
                    cancelled_orders.append(f"SL:{monitored_order.sl_order_id}")
                    logger.info(f"✅ Cancelled SL order: {monitored_order.sl_order_id}")
                if hasattr(monitored_order, 'tp_order_id') and monitored_order.tp_order_id:
                    cancelled_orders.append(f"TP:{monitored_order.tp_order_id}")
                    logger.info(f"✅ TP order was filled: {monitored_order.tp_order_id}")

            elif reason == "SL_FILLED":
                # SL was filled, cancel TP and update statuses
                await order_service.update_order_status(f"{order_ref}_sl", "FILLED")
                if hasattr(monitored_order, 'tp_order_id') and monitored_order.tp_order_id:
                    await order_service.update_order_status(f"{order_ref}_tp", "CANCELLED")
                    await broker.cancel_order(monitored_order.tp_order_id)
                    cancelled_orders.append(f"TP:{monitored_order.tp_order_id}")
                    logger.info(f"✅ Cancelled TP order: {monitored_order.tp_order_id}")
                if hasattr(monitored_order, 'sl_order_id') and monitored_order.sl_order_id:
                    cancelled_orders.append(f"SL:{monitored_order.sl_order_id}")
                    logger.info(f"✅ SL order was filled: {monitored_order.sl_order_id}")

            else:
                # Regular cleanup - cancel both orders
                if hasattr(monitored_order, 'tp_order_id') and monitored_order.tp_order_id:
                    await order_service.update_order_status(f"{order_ref}_tp", "CANCELLED")
                    try:
                        await broker.cancel_order(monitored_order.tp_order_id)
                        cancelled_orders.append(f"TP:{monitored_order.tp_order_id}")
                        logger.info(f"✅ Cancelled TP order: {monitored_order.tp_order_id}")
                    except Exception as e:
                        logger.warning(f"Failed to cancel TP order {monitored_order.tp_order_id}: {e}")

                if hasattr(monitored_order, 'sl_order_id') and monitored_order.sl_order_id:
                    await order_service.update_order_status(f"{order_ref}_sl", "CANCELLED")
                    try:
                        await broker.cancel_order(monitored_order.sl_order_id)
                        cancelled_orders.append(f"SL:{monitored_order.sl_order_id}")
                        logger.info(f"✅ Cancelled SL order: {monitored_order.sl_order_id}")
                    except Exception as e:
                        logger.warning(f"Failed to cancel SL order {monitored_order.sl_order_id}: {e}")
            
            # Cancel all open orders for this symbol (as a safety measure)
            try:
                await broker.cancel_all_orders(monitored_order.symbol)
                logger.info(f"✅ Cancelled all orders for symbol: {monitored_order.symbol}")
            except Exception as e:
                logger.warning(f"Failed to cancel all orders for {monitored_order.symbol}: {e}")
            
            # Remove from monitoring
            self.remove_order_from_monitoring(order_ref)
            
            # Send WebSocket notification
            if cancelled_orders:
                await self._send_cleanup_notification(monitored_order, cancelled_orders, reason)
            
            logger.info(f"🧹 Cleanup completed for {order_ref}: {cancelled_orders}")
            
        except Exception as e:
            logger.error(f"Error during position cleanup for {order_ref}: {e}")
    
    async def _send_cleanup_notification(self, monitored_order: MonitoredOrder, cancelled_orders: list, reason: str):
        """Send WebSocket notification about order cleanup"""
        try:
            if monitored_order.strategy_id:
                event = WSEvent(
                    type=EventType.POSITION_CLEANUP,
                    timestamp=datetime.utcnow(),
                    data={
                        "order_ref": monitored_order.order_ref,
                        "strategy_id": monitored_order.strategy_id,
                        "symbol": monitored_order.symbol,
                        "cancelled_orders": cancelled_orders,
                        "reason": reason
                    }
                )
                
                await websocket_hub.broadcast_event(monitored_order.strategy_id, event)
                # Also broadcast to GUI subscribers
                await websocket_hub.broadcast_event("GUI", event)
                logger.info(f"📡 Sent cleanup notification for {monitored_order.order_ref}")
                
        except Exception as e:
            logger.error(f"Error sending cleanup notification: {e}")
    
    async def _execute_after_fill_actions(self, monitored_order: MonitoredOrder, fill_price: float):
        """Execute after_fill_actions when an order is filled"""
        try:
            if not monitored_order.exit_plan or 'legs' not in monitored_order.exit_plan:
                return
            
            logger.info(f"Executing after_fill_actions for order {monitored_order.order_ref} at {fill_price}")
            
            for leg in monitored_order.exit_plan['legs']:
                if not leg.get('after_fill_actions'):
                    continue
                
                for action in leg['after_fill_actions']:
                    try:
                        if action == "SET_SL_TO_BREAKEVEN":
                            await self._set_sl_to_breakeven(monitored_order, leg, fill_price)
                        elif action == "START_TRAILING_SL":
                            await self._start_trailing_sl(monitored_order, leg, fill_price)
                        else:
                            logger.warning(f"Unknown after_fill_action: {action}")
                    except Exception as e:
                        logger.error(f"Error executing after_fill_action {action}: {e}")
            
        except Exception as e:
            logger.error(f"Error executing after_fill_actions: {e}")
    
    async def _set_sl_to_breakeven(self, monitored_order: MonitoredOrder, leg: Dict[str, Any], fill_price: float):
        """Set stop loss to breakeven (entry price)"""
        try:
            if not monitored_order.entry_price:
                logger.warning(f"No entry price available for breakeven SL on order {monitored_order.order_ref}")
                return
            
            # Calculate breakeven price (entry price + small buffer for fees)
            buffer = 0.001  # 0.1% buffer
            if monitored_order.side == OrderSide.BUY:
                breakeven_price = monitored_order.entry_price * (1 + buffer)
            else:
                breakeven_price = monitored_order.entry_price * (1 - buffer)
            
            logger.info(f"Setting breakeven SL for {monitored_order.order_ref} at {breakeven_price} (entry: {monitored_order.entry_price})")
            
            # Update the monitored order's stop loss
            monitored_order.stop_loss = breakeven_price
            
            # Here you would typically:
            # 1. Update the database with new SL
            # 2. Send the new SL order to the broker
            # 3. Update monitoring parameters
            
            # For now, just log the action
            logger.info(f"Breakeven SL set for {monitored_order.order_ref} at {breakeven_price}")
            
        except Exception as e:
            logger.error(f"Error setting breakeven SL: {e}")
    
    async def _start_trailing_sl(self, monitored_order: MonitoredOrder, leg: Dict[str, Any], fill_price: float):
        """Start trailing stop loss"""
        try:
            # Get trailing parameters from the leg
            trail_config = leg.get('trail_config', {})
            trail_distance = trail_config.get('distance', 0.01)  # Default 1%
            trail_type = trail_config.get('type', 'PERCENT')  # PERCENT or FIXED
            
            logger.info(f"Starting trailing SL for {monitored_order.order_ref} with {trail_distance} {trail_type}")
            
            # Calculate initial trailing stop
            if trail_type == 'PERCENT':
                if monitored_order.side == OrderSide.BUY:
                    # Long position: trail below current price
                    trail_price = fill_price * (1 - trail_distance)
                else:
                    # Short position: trail above current price
                    trail_price = fill_price * (1 + trail_distance)
            else:
                # FIXED distance
                if monitored_order.side == OrderSide.BUY:
                    trail_price = fill_price - trail_distance
                else:
                    trail_price = fill_price + trail_distance
            
            # Update the monitored order's stop loss to start trailing
            monitored_order.stop_loss = trail_price
            
            # Mark this order for trailing (you might want to add a trailing flag)
            # monitored_order.trailing_enabled = True
            
            logger.info(f"Trailing SL started for {monitored_order.order_ref} at {trail_price}")
            
        except Exception as e:
            logger.error(f"Error starting trailing SL: {e}")
    
    async def _update_trailing_sl(self, monitored_order: MonitoredOrder, current_price: float):
        """Update trailing stop loss based on current price"""
        try:
            if not monitored_order.exit_plan or 'legs' not in monitored_order.exit_plan:
                return
            
            # Check if any legs have trailing enabled
            for leg in monitored_order.exit_plan['legs']:
                if not leg.get('after_fill_actions') or "START_TRAILING_SL" not in leg['after_fill_actions']:
                    continue
                
                trail_config = leg.get('trail_config', {})
                trail_distance = trail_config.get('distance', 0.01)
                trail_type = trail_config.get('type', 'PERCENT')
                
                # Calculate new trailing stop
                if trail_type == 'PERCENT':
                    if monitored_order.side == OrderSide.BUY:
                        new_trail_price = current_price * (1 - trail_distance)
                        # Only move SL up for long positions
                        if new_trail_price > monitored_order.stop_loss:
                            monitored_order.stop_loss = new_trail_price
                            logger.info(f"Updated trailing SL for {monitored_order.order_ref} to {new_trail_price}")
                    else:
                        new_trail_price = current_price * (1 + trail_distance)
                        # Only move SL down for short positions
                        if new_trail_price < monitored_order.stop_loss:
                            monitored_order.stop_loss = new_trail_price
                            logger.info(f"Updated trailing SL for {monitored_order.order_ref} to {new_trail_price}")
                else:
                    # FIXED distance
                    if monitored_order.side == OrderSide.BUY:
                        new_trail_price = current_price - trail_distance
                        if new_trail_price > monitored_order.stop_loss:
                            monitored_order.stop_loss = new_trail_price
                            logger.info(f"Updated trailing SL for {monitored_order.order_ref} to {new_trail_price}")
                    else:
                        new_trail_price = current_price + trail_distance
                        if new_trail_price < monitored_order.stop_loss:
                            monitored_order.stop_loss = new_trail_price
                            logger.info(f"Updated trailing SL for {monitored_order.order_ref} to {new_trail_price}")
            
        except Exception as e:
            logger.error(f"Error updating trailing SL: {e}")
    
    async def _monitor_orders(self):
        """Main monitoring loop"""
        try:
            while self._running:
                # Check for any orders that need monitoring
                await self._check_all_orders()
                
                # Wait before next check
                await asyncio.sleep(1)  # Check every second
                
        except asyncio.CancelledError:
            logger.info("Order monitoring task cancelled")
        except Exception as e:
            logger.error(f"Error in order monitoring loop: {e}")
    
    async def _check_all_orders(self):
        """Check all monitored orders for triggers"""
        try:
            # This could include additional checks like time-based triggers
            # For now, the market data callbacks handle most of the work
            
            # Clean up old orders
            current_time = datetime.utcnow()
            orders_to_remove = []
            
            for order_ref, monitored_order in self.monitored_orders.items():
                # Remove orders older than 24 hours (configurable)
                if (current_time - monitored_order.created_at).total_seconds() > 86400:
                    orders_to_remove.append(order_ref)
            
            for order_ref in orders_to_remove:
                self.remove_order_from_monitoring(order_ref)
                
        except Exception as e:
            logger.error(f"Error checking all orders: {e}")
    
    def add_trigger_callback(self, callback: Callable[[MonitoredOrder, str, float], None]):
        """Add callback for order triggers"""
        self._trigger_callbacks.append(callback)
    
    def get_monitored_orders(self) -> Dict[str, MonitoredOrder]:
        """Get all currently monitored orders"""
        return self.monitored_orders.copy()
    
    def get_monitored_order(self, order_ref: str) -> Optional[MonitoredOrder]:
        """Get a specific monitored order"""
        return self.monitored_orders.get(order_ref)
    
    def is_monitoring(self, order_ref: str) -> bool:
        """Check if an order is being monitored"""
        return order_ref in self.monitored_orders
    
    def get_monitoring_stats(self) -> Dict[str, Any]:
        """Get monitoring service statistics"""
        return {
            "total_monitored": len(self.monitored_orders),
            "running": self._running,
            "symbols_subscribed": list(mexc_market_data.get_subscribed_symbols()),
            "market_data_connected": mexc_market_data.is_connected(),
            "orders": [
                {
                    "order_ref": order.order_ref,
                    "symbol": order.symbol,
                    "side": order.side.value if hasattr(order.side, 'value') else str(order.side),
                    "status": order.status,
                    "has_exit_plan": order.exit_plan is not None,
                    "last_check": order.last_check.isoformat() if order.last_check else None
                }
                for order in self.monitored_orders.values()
            ]
        }
    
    def log_monitoring_status(self):
        """Log current monitoring status for debugging"""
        logger.info(f"📊 Order Monitoring Status:")
        logger.info(f"   Running: {self._running}")
        logger.info(f"   Monitored orders: {len(self.monitored_orders)}")
        for order_ref, order in self.monitored_orders.items():
            logger.info(f"   Order {order_ref}: {order.symbol} {order.side} - {order.status}")
            if order.exit_plan:
                for leg in order.exit_plan.get('legs', []):
                    logger.info(f"     {leg.get('kind')} at ${leg.get('trigger', {}).get('value', 'N/A'):,.2f}")
    
    async def add_post_only_order_for_monitoring(self, order_ref: str, symbol: str, side: OrderSide, 
                                                quantity: float, price: float, position_id: str, 
                                                original_monitored_order: MonitoredOrder, order_type: str = "TP"):
        """Add any post-only order for monitoring to handle cancellations"""
        try:
            logger.info(f"🔍 Adding post-only {order_type} order {order_ref} for monitoring")
            
            # Create a monitored order for the post-only order
            monitored_order = MonitoredOrder(
                order_ref=order_ref,
                symbol=symbol,
                side=side,
                order_type=OrderType.LIMIT,
                quantity=quantity,
                price=price,
                created_at=datetime.utcnow(),
                last_check=datetime.utcnow(),
                status=f"MONITORING_POST_ONLY_{order_type}"
            )
            
            # Store reference to original monitored order for after_fill_actions
            monitored_order.original_request = original_monitored_order
            
            self.monitored_orders[order_ref] = monitored_order
            
            logger.info(f"✅ Added post-only {order_type} order {order_ref} for monitoring")
            
        except Exception as e:
            logger.error(f"Error adding post-only {order_type} for monitoring: {e}")
    
    async def handle_post_only_cancellation(self, order_ref: str):
        """Handle when any post-only order is cancelled (crossed the books)"""
        try:
            logger.info(f"🔄 Post-only order {order_ref} was cancelled - executing market order")
            
            if order_ref not in self.monitored_orders:
                logger.warning(f"❌ Post-only order {order_ref} not found in monitoring")
                return
            
            monitored_order = self.monitored_orders[order_ref]
            
            # Check if this is a post-only order
            if not monitored_order.status.startswith("MONITORING_POST_ONLY_"):
                logger.info(f"ℹ️ Order {order_ref} is not a post-only order")
                return
            
            # Get broker connection
            await broker_manager.ensure_broker_connected("mexc")
            broker = broker_manager.get_adapter("mexc")
            
            if not broker:
                logger.error("❌ No broker connection available")
                return
            
            # Execute market order with same volume
            logger.info(f"🚀 Executing market order for cancelled post-only order: {monitored_order.quantity} {monitored_order.symbol}")
            
            # Determine order side based on the order side
            # For SHORT positions, TP is BUY (close short)
            # For LONG positions, TP is SELL (close long)
            if monitored_order.side == OrderSide.BUY:  # Close short
                order_side = OrderSide.CloseShort
            else:  # Close long
                order_side = OrderSide.CloseLong
            
            # Place market order
            market_order_result = await broker.place_order(
                symbol=monitored_order.symbol,
                side=order_side,
                order_type=OrderType.MarketOrder,
                quantity=monitored_order.quantity,
                position_id=monitored_order.original_request.broker_position_id if monitored_order.original_request else None
            )
            
            if market_order_result.get('success'):
                logger.info(f"✅ Market order executed for cancelled post-only order: {market_order_result.get('broker_order_id')}")
                
                # Execute after_fill_actions if this was TP1 and has after_fill_actions
                if monitored_order.original_request and monitored_order.original_request.exit_plan:
                    try:
                        # Check if this was TP1 (first TP in exit plan)
                        legs = monitored_order.original_request.exit_plan.get('legs', [])
                        if legs and len(legs) > 0 and legs[0].get('kind') == 'TP':
                            logger.info(f"🎯 Executing after_fill_actions for TP1 market execution")
                            await self._execute_after_fill_actions_for_tp(monitored_order.original_request, monitored_order.price)
                    except Exception as e:
                        logger.error(f"Error executing after_fill_actions for market order: {e}")
                
                # Remove from monitoring
                self.remove_order_from_monitoring(order_ref)
            else:
                logger.error(f"❌ Failed to execute market order for cancelled post-only order: {market_order_result.get('error')}")
            
        except Exception as e:
            logger.error(f"Error handling post-only cancellation: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
    
    # Keep the old method for backward compatibility
    async def add_post_only_tp_for_monitoring(self, order_ref: str, symbol: str, side: OrderSide, 
                                            quantity: float, price: float, position_id: str, 
                                            original_monitored_order: MonitoredOrder):
        """Add a post-only TP order for monitoring to handle cancellations"""
        return await self.add_post_only_order_for_monitoring(
            order_ref, symbol, side, quantity, price, position_id, 
            original_monitored_order, "TP"
        )
    
    async def handle_post_only_tp_cancellation(self, order_ref: str):
        """Handle when a post-only TP order is cancelled (crossed the books)"""
        return await self.handle_post_only_cancellation(order_ref)
    
    async def _execute_after_fill_actions_for_tp(self, monitored_order: MonitoredOrder, fill_price: float):
        """Execute after_fill_actions for TP orders"""
        try:
            if not monitored_order.exit_plan:
                logger.info("No exit plan found for after_fill_actions")
                return
            
            legs = monitored_order.exit_plan.get('legs', [])
            if not legs:
                logger.info("No legs found in exit plan")
                return
            
            # Find TP1 leg
            tp1_leg = None
            for leg in legs:
                if leg.get('kind') == 'TP':
                    tp1_leg = leg
                    break
            
            if not tp1_leg:
                logger.info("No TP leg found in exit plan")
                return
            
            # Check for after_fill_actions
            after_fill_actions = tp1_leg.get('after_fill_actions', [])
            if not after_fill_actions:
                logger.info("No after_fill_actions found for TP1")
                return
            
            logger.info(f"🎯 Executing {len(after_fill_actions)} after_fill_actions for TP1")
            
            for action in after_fill_actions:
                action_type = action.get('action')
                logger.info(f"🎯 Executing action: {action_type}")
                
                if action_type == "SET_SL_TO_BREAKEVEN":
                    await self._set_sl_to_breakeven(monitored_order, fill_price)
                elif action_type == "START_TRAILING_SL":
                    await self._start_trailing_sl(monitored_order, action)
                else:
                    logger.warning(f"Unknown after_fill_action: {action_type}")
            
        except Exception as e:
            logger.error(f"Error executing after_fill_actions: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
    
    async def _set_sl_to_breakeven(self, monitored_order: MonitoredOrder, fill_price: float):
        """Set SL to breakeven (entry price)"""
        try:
            # Check if we already moved SL to breakeven
            if getattr(monitored_order, 'sl_moved_to_breakeven', False):
                logger.debug(f"🎯 SL already moved to breakeven for order {monitored_order.order_ref}, skipping")
                return
                
            logger.info(f"🎯 Setting SL to breakeven for order {monitored_order.order_ref}")
            
            # Get broker connection
            await broker_manager.ensure_broker_connected("mexc")
            broker = broker_manager.get_adapter("mexc")
            
            if not broker:
                logger.error("❌ No broker connection available")
                return
            
            # Get entry price from position
            entry_price = monitored_order.entry_price
            if not entry_price:
                logger.error("❌ No entry price found for breakeven SL")
                return
            
            logger.info(f"🎯 Entry price: {entry_price}, Fill price: {fill_price}")
            logger.info(f"🎯 Setting SL to breakeven at: {entry_price}")
            
            # Update the attached SL to breakeven
            if hasattr(broker, 'modify_attached_sl_tp'):
                # Use cached entry broker order id if available
                broker_order_id = None
                if getattr(monitored_order, 'entry_broker_order_id', None):
                    broker_order_id = str(monitored_order.entry_broker_order_id)
                    logger.info(f"🎯 Using cached entry broker order id: {broker_order_id}")
                else:
                    # Fetch entry order's broker order id from order logs using order_ref
                    try:
                        from .orders import order_service
                        entry_order_data = await order_service.get_order_by_ref(monitored_order.order_ref)
                        if not entry_order_data or not entry_order_data.get('broker_order_id'):
                            logger.error(f"❌ Could not find broker_order_id for entry order {monitored_order.order_ref}")
                            return
                        broker_order_id = str(entry_order_data['broker_order_id'])
                        # Cache it for next time
                        monitored_order.entry_broker_order_id = broker_order_id
                        logger.info(f"🎯 Caching entry broker order id: {broker_order_id}")
                    except Exception as e:
                        logger.error(f"❌ Failed to load entry order data for {monitored_order.order_ref}: {e}")
                        return

                logger.info(f"🎯 Updating attached SL on broker order {broker_order_id} to breakeven {entry_price}")
                result = await broker.modify_attached_sl_tp(
                    order_id=broker_order_id,
                    stop_loss_price=entry_price,
                    take_profit_price=None
                )
                
                if result.get('success'):
                    logger.info(f"✅ SL moved to breakeven successfully")
                    # Set flag to prevent repeated moves
                    monitored_order.sl_moved_to_breakeven = True
                else:
                    logger.error(f"❌ Failed to move SL to breakeven: {result.get('error')}")
            else:
                logger.error("❌ Broker does not support modify_attached_sl_tp")
            
        except Exception as e:
            logger.error(f"Error setting SL to breakeven: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
    
    async def _start_trailing_sl(self, monitored_order: MonitoredOrder, action: dict):
        """Start trailing stop loss"""
        try:
            logger.info(f"🎯 Starting trailing SL for order {monitored_order.order_ref}")
            # Implementation for trailing SL
            # This would involve setting up trailing logic
            pass
        except Exception as e:
            logger.error(f"Error starting trailing SL: {e}")

# Global order monitor service instance
order_monitor = OrderMonitorService()
