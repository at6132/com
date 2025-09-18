"""
MEXC broker adapter implementation
Uses the MEXC Python SDK for order execution
"""
import logging
import asyncio
from typing import Dict, Any, Optional, List
from datetime import datetime
import time # Added for caching

# Import MEXC SDK from local package
import sys
import os
from pathlib import Path

# Setup logger first
logger = logging.getLogger(__name__)

# Add the mexc_python directory to Python path
mexc_path = Path(__file__).parent.parent.parent.parent / "mexc_python"
if mexc_path.exists():
    sys.path.insert(0, str(mexc_path))

try:
    from mexcpy.api import MexcFuturesAPI
    from mexcpy.mexcTypes import (
        CreateOrderRequest, OrderSide, OrderType, OpenType, 
        PositionMode, TriggerOrderRequest, TriggerType, 
        ExecuteCycle, TriggerPriceType
    )
    MEXC_AVAILABLE = True
    logger.info(f"MEXC Python SDK loaded from: {mexc_path}")
except ImportError as e:
    MEXC_AVAILABLE = False
    logger.error(f"MEXC Python SDK not available: {e}")
    logger.error(f"Expected path: {mexc_path}")
    logger.error("Please ensure the mexc_python package is properly set up")

from .base import BrokerAdapter
from ..config.brokers import MEXCConfig, BaseUnit
from ..schemas.orders import OrderRequest, OrderView
from ..schemas.base import OrderSide as COMSide, OrderType as COMOrderType

class MEXCAdapter(BrokerAdapter):
    """MEXC broker adapter implementation"""
    
    def __init__(self, config: MEXCConfig):
        super().__init__(config)
        self.config: MEXCConfig = config
        self.api: Optional[MexcFuturesAPI] = None
        self._connected = False
    
    async def connect(self) -> bool:
        """Connect to MEXC API"""
        if not MEXC_AVAILABLE:
            logger.error("MEXC Python SDK not available")
            return False
        
        try:
            # Initialize MEXC API client with token
            self.api = MexcFuturesAPI(
                token=self.config.token or "",
                testnet=self.config.testnet
            )
            
            # Skip expensive health check during initialization
            # Just mark as connected - health check will happen on first real request
            self._connected = True
            logger.info(f"Connected to MEXC {'testnet' if self.config.testnet else 'live'}")
            return True
                
        except Exception as e:
            logger.error(f"Error connecting to MEXC: {e}")
            return False
    
    async def disconnect(self):
        """Disconnect from MEXC API"""
        self._connected = False
        self.api = None
        logger.info("Disconnected from MEXC API")
    
    async def health_check(self) -> bool:
        """Check MEXC API connectivity with caching"""
        if not self.api:
            return False
        
        # Use cached health status if recent
        current_time = time.time()
        if hasattr(self, '_last_health_check') and hasattr(self, '_cached_health_status'):
            # Cache health status for 30 seconds
            if current_time - self._last_health_check < 30:
                return self._cached_health_status
        
        try:
            # Try to get account info as a health check
            result = await self.api.get_user_assets()
            health_status = result.success
            
            # Cache the result
            self._cached_health_status = health_status
            self._last_health_check = current_time
            
            return health_status
        except Exception as e:
            logger.error(f"MEXC health check failed: {e}")
            # Cache failure for 10 seconds to avoid hammering API
            self._cached_health_status = False
            self._last_health_check = current_time
            return False
    
    def _map_order_side(self, side: COMSide) -> OrderSide:
        """Map COM order side to MEXC order side"""
        if side == COMSide.BUY:
            return OrderSide.OpenLong
        elif side == COMSide.SELL:
            return OrderSide.OpenShort
        else:
            raise ValueError(f"Unsupported order side: {side}")
    
    def _map_order_type(self, order_type: COMOrderType) -> OrderType:
        """Map COM order type to MEXC order type"""
        if order_type == COMOrderType.MARKET:
            return OrderType.MarketOrder
        elif order_type == COMOrderType.LIMIT:
            return OrderType.PriceLimited
        elif order_type == COMOrderType.STOP:
            return OrderType.PriceLimited  # MEXC uses trigger orders for stops
        elif order_type == COMOrderType.STOP_LIMIT:
            return OrderType.PriceLimited  # MEXC uses trigger orders for stop-limit
        elif order_type == COMOrderType.POST_ONLY:
            return OrderType.PostOnlyMaker
        else:
            raise ValueError(f"Unsupported order type: {order_type}")
    
    def _map_open_type(self, leverage_enabled: bool) -> OpenType:
        """Map leverage setting to MEXC open type"""
        if leverage_enabled:
            return OpenType.Isolated
        else:
            return OpenType.Cross
    
    def _map_symbol_to_mexc(self, com_symbol: str) -> str:
        """Map COM symbol format to MEXC symbol format"""
        # MEXC uses underscore format (BTC_USDT), COM uses no underscore (BTCUSDT)
        symbol_mapping = {
            "BTCUSDT": "BTC_USDT",
            "ETHUSDT": "ETH_USDT", 
            "DOGEUSDT": "DOGE_USDT",
            "ADAUSDT": "ADA_USDT",
            "SOLUSDT": "SOL_USDT",
            "MATICUSDT": "MATIC_USDT",
            "LINKUSDT": "LINK_USDT"
        }
        return symbol_mapping.get(com_symbol, com_symbol)
    
    def _map_symbol_from_mexc(self, mexc_symbol: str) -> str:
        """Map MEXC symbol format to COM symbol format"""
        # MEXC uses underscore format (BTC_USDT), COM uses no underscore (BTCUSDT)
        symbol_mapping = {
            "BTC_USDT": "BTCUSDT",
            "ETH_USDT": "ETHUSDT",
            "DOGE_USDT": "DOGEUSDT", 
            "ADA_USDT": "ADAUSDT",
            "SOL_USDT": "SOLUSDT",
            "MATIC_USDT": "MATICUSDT",
            "LINK_USDT": "LINKUSDT"
        }
        return symbol_mapping.get(mexc_symbol, mexc_symbol)
    
    def validate_order(self, order: OrderRequest) -> Dict[str, Any]:
        """Override validate_order to use mapped symbol for validation"""
        # Map COM symbol to MEXC symbol for validation
        mapped_symbol = self._map_symbol_to_mexc(order.instrument.symbol)
        
        # Create a temporary order with mapped symbol for validation
        temp_order = order.model_copy(deep=True)
        temp_order.instrument.symbol = mapped_symbol
        
        # Call parent validation with mapped symbol
        return super().validate_order(temp_order)
    
    async def place_order(self, order: OrderRequest) -> Dict[str, Any]:
        """Place a new order with MEXC"""
        if not self._connected or not self.api:
            raise RuntimeError("Not connected to MEXC API")
        
        try:
            # Validate order
            validation = self.validate_order(order)
            logger.info(f"MEXC order validation result: {validation}")
            if not validation["valid"]:
                logger.error(f"MEXC order validation failed: {validation['errors']}")
                return {
                    "success": False,
                    "error": "Order validation failed",
                    "details": validation["errors"]
                }
            
            # Map COM order to MEXC order
            mexc_side = self._map_order_side(order.side)
            mexc_type = self._map_order_type(order.order_type)
            open_type = self._map_open_type(order.leverage.enabled if order.leverage else False)
            
            # Extract quantity
            if hasattr(order, 'quantity') and order.quantity:
                quantity = order.quantity.value
                # Snap quantity to lot size to ensure precision compliance
                quantity = self.snap_to_lot(quantity, order.instrument.symbol)
                
                # Convert quantity to broker's expected base unit
                original_quantity = quantity
                quantity = self.convert_quantity_to_broker_units(quantity, order.instrument.symbol)
                
                logger.info(f"📏 Original quantity: {order.quantity.value}, Snapped quantity: {original_quantity}")
                logger.info(f"📊 Converted to broker units: {original_quantity} → {quantity} ({self.config.base_unit.value})")
            else:
                # TODO: Calculate from risk.sizing
                raise ValueError("Quantity calculation from risk.sizing not implemented yet")
            
            # Create MEXC order request
            logger.info(f"🔧 Creating MEXC order with:")
            logger.info(f"   Symbol: {order.instrument.symbol}")
            logger.info(f"   Side: {mexc_side}")
            logger.info(f"   Quantity: {quantity} (type: {type(quantity)})")
            logger.info(f"   Order Type: {mexc_type}")
            logger.info(f"   Open Type: {open_type}")
            logger.info(f"   Leverage: {order.leverage.leverage if order.leverage and order.leverage.leverage else 1}")
            
            mexc_order = CreateOrderRequest(
                symbol=self._map_symbol_to_mexc(order.instrument.symbol),
                side=mexc_side,
                vol=quantity,
                type=mexc_type,
                openType=open_type,
                leverage=order.leverage.leverage if order.leverage and order.leverage.leverage else 1
            )
            
            # Add TP/SL prices from exit plan if present
            # For complex exit plans with multiple legs, don't attach to main order
            if hasattr(order, 'exit_plan') and order.exit_plan and order.exit_plan.legs:
                tp_count = 0
                sl_count = 0
                
                # Count TP/SL legs
                for leg in order.exit_plan.legs:
                    if leg.kind.value == "TP":
                        tp_count += 1
                    elif leg.kind.value == "SL":
                        sl_count += 1
                
                # Attach SL orders to main order, TPs will be separate
                sl_attached = False
                for leg in order.exit_plan.legs:
                    if leg.kind.value == "TP":
                        # TPs are post-only LIMIT orders - will be placed separately
                        logger.info(f"   TP at {leg.trigger['value']} will be placed as separate LIMIT order")
                    elif leg.kind.value == "SL" and not sl_attached:
                        # Only attach the first SL (MEXC only supports one stopLossPrice)
                        mexc_order.stopLossPrice = self.snap_to_tick(leg.trigger["value"], order.instrument.symbol)
                        logger.info(f"   Stop Loss Price: {mexc_order.stopLossPrice}")
                        sl_attached = True
                    elif leg.kind.value == "SL" and sl_attached:
                        # Additional SLs will be logged but not attached
                        logger.info(f"   Additional SL at {leg.trigger['value']} will be logged but not attached (MEXC limitation)")
            
            # Add TP/SL prices if this is a STOP order with stop_price
            if order.order_type == COMOrderType.STOP and order.stop_price:
                snapped_price = self.snap_to_tick(order.stop_price, order.instrument.symbol)
                
                # Check if this is a TP or SL from exit plan metadata
                if hasattr(order, '_leg_kind'):
                    if order._leg_kind == "TP":
                        mexc_order.takeProfitPrice = snapped_price
                        logger.info(f"   Take Profit Price: {mexc_order.takeProfitPrice}")
                    elif order._leg_kind == "SL":
                        mexc_order.stopLossPrice = snapped_price
                        logger.info(f"   Stop Loss Price: {mexc_order.stopLossPrice}")
                else:
                    # Fallback: assume it's SL for backward compatibility
                    mexc_order.stopLossPrice = snapped_price
                    logger.info(f"   Stop Loss Price: {mexc_order.stopLossPrice} (fallback)")
            
            # Add price for limit orders
            if order.order_type in [COMOrderType.LIMIT, COMOrderType.STOP_LIMIT] and order.price:
                mexc_order.price = self.snap_to_tick(order.price, order.instrument.symbol)
                logger.info(f"   Price: {mexc_order.price} (snapped from {order.price})")
            
            # Note: TP/SL orders are now handled directly via stopLossPrice/takeProfitPrice fields above
            
            # Add post-only flag
            if order.flags.post_only:
                mexc_order.type = OrderType.PostOnlyMaker
                logger.info(f"   Post-only flag set")
            
            # Log final MEXC order details
            logger.info(f"🔐 Final MEXC order details:")
            logger.info(f"   mexc_order.symbol: {mexc_order.symbol}")
            logger.info(f"   mexc_order.side: {mexc_order.side}")
            logger.info(f"   mexc_order.vol: {mexc_order.vol}")
            logger.info(f"   mexc_order.type: {mexc_order.type}")
            logger.info(f"   mexc_order.openType: {mexc_order.openType}")
            logger.info(f"   mexc_order.leverage: {mexc_order.leverage}")
            if hasattr(mexc_order, 'price') and mexc_order.price:
                logger.info(f"   mexc_order.price: {mexc_order.price}")
            
            # Place order
            logger.info(f"🔐 Sending MEXC order: {mexc_order}")
            result = await self.api.create_order(mexc_order)
            logger.info(f"📥 MEXC API response: {result}")
            logger.info(f"📊 MEXC response success: {result.success}")
            if hasattr(result, 'data'):
                logger.info(f"📋 MEXC response data: {result.data}")
            if hasattr(result, 'message'):
                logger.info(f"💬 MEXC response message: {result.message}")
            
            if result.success:
                # Get stop limit order ID if TP/SL were attached
                stop_limit_order_id = None
                if hasattr(mexc_order, 'stopLossPrice') or hasattr(mexc_order, 'takeProfitPrice'):
                    try:
                        # Wait longer for the stop limit order to be created
                        logger.info(f"🔧 Waiting for stop limit order to be created for order {result.data.orderId}")
                        await asyncio.sleep(3)  # Increased from 1 to 3 seconds
                        stop_limit_order_id = await self.get_stop_limit_order_id(str(result.data.orderId))
                        if stop_limit_order_id:
                            logger.info(f"🔧 Captured stop limit order ID: {stop_limit_order_id} for order {result.data.orderId}")
                        else:
                            logger.warning(f"⚠️ Could not capture stop limit order ID for order {result.data.orderId}")
                    except Exception as e:
                        logger.warning(f"⚠️ Could not capture stop limit order ID: {e}")
                
                return {
                    "success": True,
                    "broker_order_id": str(result.data.orderId),
                    "status": "ACCEPTED",
                    "broker_response": result.data,
                    "stop_limit_order_id": stop_limit_order_id
                }
            else:
                logger.error(f"❌ MEXC order placement failed!")
                logger.error(f"📊 Response success: {result.success}")
                if hasattr(result, 'data'):
                    logger.error(f"📋 Response data: {result.data}")
                if hasattr(result, 'message'):
                    logger.error(f"💬 Response message: {result.message}")
                if hasattr(result, 'code'):
                    logger.error(f"🔢 Response code: {result.code}")
                
                return {
                    "success": False,
                    "error": "MEXC order placement failed",
                    "details": result
                }
                
        except Exception as e:
            logger.error(f"💥 Exception during MEXC order placement: {e}")
            logger.error(f"📝 Exception type: {type(e).__name__}")
            import traceback
            logger.error(f"🔍 Full traceback: {traceback.format_exc()}")
            return {
                "success": False,
                "error": str(e),
                "details": None
            }
    
    async def amend_order(self, broker_order_id: str, changes: Dict[str, Any]) -> Dict[str, Any]:
        """Amend an existing MEXC order"""
        if not self._connected or not self.api:
            raise RuntimeError("Not connected to MEXC API")
        
        try:
            # MEXC doesn't support direct order amendment
            # We need to cancel and recreate
            cancel_result = await self.cancel_order(broker_order_id)
            if not cancel_result["success"]:
                return {
                    "success": False,
                    "error": "Failed to cancel order for amendment",
                    "details": cancel_result
                }
            
            # TODO: Recreate order with changes
            # This requires storing the original order details
            return {
                "success": False,
                "error": "Order amendment not fully implemented yet",
                "details": "Need to implement order recreation logic"
            }
            
        except Exception as e:
            logger.error(f"Error amending MEXC order: {e}")
            return {
                "success": False,
                "error": str(e),
                "details": None
            }
    
    async def cancel_order(self, broker_order_id: str) -> Dict[str, Any]:
        """Cancel an existing MEXC order"""
        if not self._connected or not self.api:
            raise RuntimeError("Not connected to MEXC API")
        
        try:
            # Try to cancel as regular order first
            result = await self.api.cancel_orders([broker_order_id])
            
            if result.success:
                return {
                    "success": True,
                    "status": "CANCELLED",
                    "broker_response": result.data
                }
            else:
                # If regular order cancel fails, try trigger order cancel
                try:
                    trigger_result = await self.api.cancel_trigger_orders([{"orderId": broker_order_id}])
                    if trigger_result.success:
                        return {
                            "success": True,
                            "status": "CANCELLED",
                            "order_type": "TRIGGER",
                            "broker_response": trigger_result.data
                        }
                except:
                    pass
                
                return {
                    "success": False,
                    "error": "MEXC order cancellation failed",
                    "details": result
                }
                
        except Exception as e:
            logger.error(f"Error cancelling MEXC order: {e}")
            return {
                "success": False,
                "error": str(e),
                "details": None
            }
    
    async def get_order(self, broker_order_id: str) -> Optional[Dict[str, Any]]:
        """Get order status from MEXC"""
        if not self._connected or not self.api:
            return None
        
        try:
            result = await self.api.get_order_by_order_id(broker_order_id)
            
            if result.success and result.data:
                order_data = result.data
                return {
                    "broker_order_id": broker_order_id,
                    "status": order_data.state,
                    "filled_qty": order_data.dealVol if hasattr(order_data, 'dealVol') else 0,
                    "remaining_qty": order_data.vol - (order_data.dealVol if hasattr(order_data, 'dealVol') else 0),
                    "price": order_data.price,
                    "side": order_data.side,
                    "symbol": order_data.symbol,
                    "order_type": order_data.orderType,
                    "externalOid": getattr(order_data, 'externalOid', ''),
                    "broker_data": order_data
                }
            else:
                # Try to get as trigger order
                try:
                    # Note: MEXC doesn't have a direct way to get trigger order by ID
                    # This would need to be implemented by querying all trigger orders
                    return None
                except:
                    return None
                
        except Exception as e:
            logger.error(f"Error getting MEXC order: {e}")
            return None
    
    async def get_balances(self) -> Dict[str, float]:
        """Get MEXC account balances"""
        if not self._connected or not self.api:
            logger.warning("MEXC adapter not connected, returning empty balances")
            return {}
        
        try:
            # Log which environment we're fetching from
            logger.info(f"🔍 Fetching MEXC balances from {'testnet' if self.config.testnet else 'live'} account")
            logger.info(f"🔍 Using token: {self.config.token[:10]}...")
            
            result = await self.api.get_user_assets()
            logger.info(f"🔍 MEXC get_user_assets result: success={result.success}, data_length={len(result.data) if result.data else 0}")
            
            if result.success and result.data:
                balances = {}
                for asset in result.data:
                    # Handle both AssetInfo objects and raw dictionaries
                    if hasattr(asset, 'currency') and hasattr(asset, 'availableBalance'):
                        # AssetInfo object
                        balances[asset.currency] = asset.availableBalance
                        logger.info(f"🔍 Found balance: {asset.currency} = {asset.availableBalance}")
                    elif isinstance(asset, dict):
                        # Raw dictionary from API
                        currency = asset.get('currency', '')
                        available_balance = asset.get('availableBalance', 0.0)
                        if currency:
                            balances[currency] = float(available_balance)
                            logger.info(f"🔍 Found balance: {currency} = {available_balance}")
                    else:
                        logger.warning(f"Unexpected asset data type: {type(asset)}, data: {asset}")
                
                logger.info(f"🔍 Final balances: {balances}")
                return balances
            else:
                logger.error(f"Failed to get MEXC balances: {result}")
                return {}
        except Exception as e:
            logger.error(f"Error getting MEXC balances: {e}")
            return {}
    
    async def get_positions(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get current MEXC positions"""
        if not self._connected or not self.api:
            return []
        
        try:
            # Get all positions and filter by symbol if needed
            result = await self.api.get_open_positions(None)

            # If we want to filter by symbol, do it manually
            if result.success and result.data and symbol:
                filtered_data = [pos for pos in result.data if getattr(pos, 'symbol', '') == symbol or (isinstance(pos, dict) and pos.get('symbol') == symbol)]
                result.data = filtered_data
            if not result.success:
                return []

            if result.data:
                positions = []
                for pos in result.data:
                    # Handle both object and dictionary formats
                    if isinstance(pos, dict):
                        position_data = {
                            "symbol": pos.get("symbol", ""),
                            "side": "LONG" if pos.get("positionType", 0) == 1 else "SHORT",
                            "size": pos.get("holdVol", 0.0),  # Use holdVol instead of vol
                            "entry_price": pos.get("openAvgPrice", 0.0),  # Use openAvgPrice
                            "mark_price": pos.get("holdAvgPrice", 0.0),  # Use holdAvgPrice
                            "unrealized_pnl": pos.get("realised", 0.0),  # Use realised PnL
                            "margin": pos.get("im", 0.0),  # Use initial margin
                            "leverage": pos.get("leverage", 1),
                            "position_id": pos.get("positionId", ""),
                            "state": pos.get("state", 0),  # Add position state
                            "hold_vol": pos.get("holdVol", 0.0),  # Add hold volume
                            "frozen_vol": pos.get("frozenVol", 0.0)  # Add frozen volume
                        }
                        positions.append(position_data)
                    else:
                        # Handle object format
                        position_data = {
                            "symbol": getattr(pos, 'symbol', ''),
                            "side": "LONG" if getattr(pos, 'positionType', 0) == 1 else "SHORT",
                            "size": getattr(pos, 'holdVol', 0.0),  # Use holdVol instead of vol
                            "entry_price": getattr(pos, 'openAvgPrice', 0.0),  # Use openAvgPrice
                            "mark_price": getattr(pos, 'holdAvgPrice', 0.0),  # Use holdAvgPrice
                            "unrealized_pnl": getattr(pos, 'realised', 0.0),  # Use realised PnL
                            "margin": getattr(pos, 'im', 0.0),  # Use initial margin
                            "leverage": getattr(pos, 'leverage', 1),
                            "position_id": getattr(pos, 'positionId', ''),
                            "state": getattr(pos, 'state', 0),  # Add position state
                            "hold_vol": getattr(pos, 'holdVol', 0.0),  # Add hold volume
                            "frozen_vol": getattr(pos, 'frozenVol', 0.0)  # Add frozen volume
                        }
                        positions.append(position_data)
                return positions
            else:
                logger.error(f"Failed to get MEXC positions: {result}")
                return []
        except Exception as e:
            logger.error(f"Error getting MEXC positions: {e}")
            return []
    
    async def get_market_data(self, symbol: str) -> Dict[str, Any]:
        """Get current MEXC market data from internal market data service"""
        try:
            from ..services.mexc_market_data import mexc_market_data
            
            # Get real-time market data from internal service
            market_data = mexc_market_data.get_market_data(symbol)
            if market_data:
                return {
                    "symbol": symbol,
                    "bid": market_data.bid,
                    "ask": market_data.ask,
                    "last": market_data.last_price,
                    "volume": market_data.volume,
                    "timestamp": market_data.timestamp.isoformat(),
                    "spread_bps": market_data.spread_bps
                }
            else:
                # Fallback to placeholder data if no market data available
                logger.warning(f"No market data available for {symbol}, using placeholder")
                return {
                    "symbol": symbol,
                    "bid": 50000.0,
                    "ask": 50001.0,
                    "last": 50000.5,
                    "volume": 100.0,
                    "timestamp": datetime.utcnow().isoformat(),
                    "note": "Using placeholder data - no real-time data available"
                }
        except Exception as e:
            logger.error(f"Error getting market data for {symbol}: {e}")
            return {
                "symbol": symbol,
                "bid": 0.0,
                "ask": 0.0,
                "last": 0.0,
                "volume": 0.0,
                "timestamp": datetime.utcnow().isoformat(),
                "error": str(e)
            }
    
    async def _create_stop_order(self, order: OrderRequest, quantity: float) -> Dict[str, Any]:
        """Create a stop order using MEXC trigger order system"""
        try:
            # Determine trigger type based on side
            if order.side == COMSide.BUY:
                trigger_type = TriggerType.GreaterThanOrEqual  # Buy when price goes up
            else:
                trigger_type = TriggerType.LessThanOrEqual  # Sell when price goes down
            
            # Create trigger order request
            trigger_request = TriggerOrderRequest(
                symbol=self._map_symbol_to_mexc(order.instrument.symbol),
                side=self._map_order_side(order.side),
                vol=quantity,
                openType=self._map_open_type(order.leverage.enabled if order.leverage else False),
                triggerPrice=self.snap_to_tick(order.stop_price, order.instrument.symbol),
                triggerType=trigger_type,
                executeCycle=ExecuteCycle.UntilCanceled,
                orderType=OrderType.MarketOrder,  # Execute as market order
                trend=TriggerPriceType.LatestPrice,
                leverage=order.leverage.leverage if order.leverage and order.leverage.leverage else 1
            )
            
            # Place trigger order
            result = await self.api.create_trigger_order(trigger_request)
            
            if result.success:
                return {
                    "success": True,
                    "broker_order_id": str(result.data),
                    "status": "ACCEPTED",
                    "order_type": "TRIGGER",
                    "broker_response": result.data
                }
            else:
                return {
                    "success": False,
                    "error": "MEXC trigger order placement failed",
                    "details": result
                }
                
        except Exception as e:
            logger.error(f"Error creating MEXC stop order: {e}")
            return {
                "success": False,
                "error": str(e),
                "details": None
            }
    
    async def get_features(self) -> Dict[str, Any]:
        """Get MEXC features and capabilities"""
        return self.config.features
    
    async def get_market_info(self, symbol: str) -> Dict[str, Any]:
        """Get MEXC market information for a specific symbol"""
        # Map COM symbol to MEXC symbol for lookup
        mapped_symbol = self._map_symbol_to_mexc(symbol)
        
        for market_type, market_config in self.config.markets.items():
            symbols = market_config.get("symbols", {})
            if isinstance(symbols, dict) and mapped_symbol in symbols:
                return {
                    "symbol": symbol,  # Return original COM symbol
                    "market_type": market_type,
                    **symbols[mapped_symbol]  # Include all symbol-specific parameters
                }
            elif isinstance(symbols, list) and mapped_symbol in symbols:
                # Fallback for old format
                return {
                    "symbol": symbol,  # Return original COM symbol
                    "market_type": market_type,
                    **market_config
                }
        return {}
    
    async def get_recent_trades(self, symbol: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent trades for a symbol using order transactions"""
        if not self._connected or not self.api:
            return []
        
        try:
            # Map symbol to MEXC format
            mexc_symbol = self._map_symbol_to_mexc(symbol)
            
            # Get recent order transactions for this symbol
            result = await self.api.get_order_transactions_by_symbol(
                symbol=mexc_symbol, 
                page_size=limit
            )
            
            if result.success and result.data:
                trades = []
                for transaction in result.data:
                    # Handle both dict and object responses
                    if hasattr(transaction, 'id'):
                        # Transaction object
                        trade_data = {
                            'id': transaction.id,
                            'symbol': transaction.symbol,
                            'side': transaction.side,
                            'type': getattr(transaction, 'type', 'UNKNOWN'),
                            'quantity': float(transaction.vol),
                            'price': float(transaction.price),
                            'time': transaction.time,
                            'fee': float(transaction.fee),
                            'pnl': float(getattr(transaction, 'pnl', 0)),
                            'order_id': getattr(transaction, 'orderId', getattr(transaction, 'order_id', ''))
                        }
                        # Quiet raw attribute dumps
                        # logger.debug(...) left out on purpose
                    else:
                        # Dictionary response
                        trade_data = {
                            'id': transaction.get('id', ''),
                            'symbol': transaction.get('symbol', ''),
                            'side': transaction.get('side', ''),
                            'type': transaction.get('type', 'UNKNOWN'),
                            'quantity': float(transaction.get('vol', 0)),
                            'price': float(transaction.get('price', 0)),
                            'time': transaction.get('time', 0),
                            'fee': float(transaction.get('fee', 0)),
                            'pnl': float(transaction.get('pnl', 0)),
                            'order_id': transaction.get('orderId', transaction.get('order_id', ''))
                        }
                        # Quiet raw dict dump
                        # logger.debug(...) left out on purpose
                    trades.append(trade_data)
                return trades
            else:
                logger.warning(f"Failed to get recent trades for {symbol}: {result}")
                return []
                
        except Exception as e:
            logger.error(f"Error getting recent trades for {symbol}: {e}")
            return []
    
    async def get_historical_orders(self, symbol: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Get historical orders for a symbol to determine close reasons"""
        if not self._connected or not self.api:
            return []
        
        try:
            # Map symbol to MEXC format
            mexc_symbol = self._map_symbol_to_mexc(symbol)
            
            # Get historical orders for this symbol
            result = await self.api.get_historical_orders(
                symbol=mexc_symbol,
                page_size=limit
            )
            
            if result.success and result.data:
                orders = []
                for order in result.data:
                    # Handle both dict and object responses
                    if hasattr(order, 'id'):
                        # Order object
                        order_data = {
                            'id': order.id,
                            'symbol': order.symbol,
                            'side': order.side,
                            'type': getattr(order, 'type', 'UNKNOWN'),
                            'state': getattr(order, 'state', 'UNKNOWN'),
                            'quantity': float(order.vol),
                            'price': float(order.price),
                            'time': order.time,
                            'category': getattr(order, 'category', 'UNKNOWN')
                        }
                    else:
                        # Dictionary response
                        order_data = {
                            'id': order.get('id', ''),
                            'symbol': order.get('symbol', ''),
                            'side': order.get('side', ''),
                            'type': order.get('type', 'UNKNOWN'),
                            'state': order.get('state', 'UNKNOWN'),
                            'quantity': float(order.get('vol', 0)),
                            'price': float(order.get('price', 0)),
                            'time': order.get('time', 0),
                            'category': order.get('category', 'UNKNOWN')
                        }
                    orders.append(order_data)
                return orders
            else:
                logger.warning(f"Failed to get historical orders for {symbol}: {result}")
                return []
                
        except Exception as e:
            logger.error(f"Error getting historical orders for {symbol}: {e}")
            return []

    async def get_position_close_data(self, symbol: str, position_id: str = None) -> Dict[str, Any]:
        """Get position close data including exact exit price, time, PnL, and fees"""
        if not self._connected or not self.api:
            return {}
        
        try:
            # Map symbol to MEXC format
            mexc_symbol = self._map_symbol_to_mexc(symbol)
            
            # First try to get data from historical positions (more comprehensive)
            if position_id:
                try:
                    logger.info(f"🔍 Looking for position {position_id} in historical positions for {symbol}")
                    
                    # Get historical positions to find the specific position
                    result = await self.api.get_historical_positions(
                        symbol=mexc_symbol,
                        page_num=1,
                        page_size=50
                    )
                    
                    logger.info(f"📊 Historical positions API response: success={result.success}, data_count={len(result.data) if result.data else 0}")
                    
                    if result.success and result.data:
                        # Print all position IDs we found for debugging
                        found_position_ids = []
                        for pos in result.data:
                            if hasattr(pos, 'positionId'):
                                found_position_ids.append(pos.positionId)
                            elif isinstance(pos, dict):
                                found_position_ids.append(pos.get('positionId'))
                        
                        logger.info(f"📋 Found position IDs in historical data: {found_position_ids}")
                        
                        # Look for the specific position ID
                        for pos in result.data:
                            pos_id = None
                            if hasattr(pos, 'positionId'):
                                pos_id = pos.positionId
                            elif isinstance(pos, dict):
                                pos_id = pos.get('positionId')
                            
                            if str(pos_id) == str(position_id):
                                logger.info(f"✅ Found matching position {position_id}")
                                logger.info(f"📊 Raw position data: {pos}")
                                
                                # Found the position - extract comprehensive data
                                # Handle both dict and object formats
                                if isinstance(pos, dict):
                                    # Use volume (position size) as margin - no calculations
                                    leverage = float(pos.get('leverage', 1))
                                    margin_used = float(pos.get('closeVol', 0))  # Just use the volume
                                    logger.info(f"📊 Using volume as margin: {margin_used}")
                                    
                                    close_data = {
                                        'exit_price': float(pos.get('closeAvgPrice', 0)),
                                        'exit_time': datetime.fromtimestamp(pos.get('updateTime', 0) / 1000) if pos.get('updateTime') else None,
                                        'total_pnl_usd': float(pos.get('realised', 0)),
                                        'total_fees': float(pos.get('totalFee', 0)),
                                        'leverage': leverage,
                                        'margin_used': margin_used,  # Use MEXC margin data or calculated fallback
                                        'position_id': pos.get('positionId'),
                                        'close_profit_loss': float(pos.get('closeProfitLoss', 0)),
                                        'profit_ratio': float(pos.get('profitRatio', 0))
                                    }
                                else:
                                    # Object format - use volume as margin - no calculations
                                    leverage = float(getattr(pos, 'leverage', 1))
                                    margin_used = float(getattr(pos, 'closeVol', 0))  # Just use the volume
                                    logger.info(f"📊 Using volume as margin (object): {margin_used}")
                                    
                                    close_data = {
                                        'exit_price': float(pos.closeAvgPrice) if hasattr(pos, 'closeAvgPrice') else 0.0,
                                        'exit_time': datetime.fromtimestamp(pos.updateTime / 1000) if hasattr(pos, 'updateTime') and pos.updateTime else None,
                                        'total_pnl_usd': float(pos.realised) if hasattr(pos, 'realised') else 0.0,
                                        'total_fees': float(pos.totalFee) if hasattr(pos, 'totalFee') else 0.0,
                                        'leverage': leverage,
                                        'margin_used': margin_used,  # Use MEXC margin data or calculated fallback
                                        'position_id': pos.positionId,
                                        'close_profit_loss': float(pos.closeProfitLoss) if hasattr(pos, 'closeProfitLoss') else 0.0,
                                        'profit_ratio': float(pos.profitRatio) if hasattr(pos, 'profitRatio') else 0.0
                                    }
                                
                                logger.info(f"📊 Extracted close data: {close_data}")
                                logger.info(f"📊 Found position {position_id} in historical data: PnL=${close_data['total_pnl_usd']:.2f}, Fees=${close_data['total_fees']:.4f}, Leverage={close_data['leverage']}, Margin=${close_data['margin_used']:.2f}")
                                return close_data
                        
                        logger.warning(f"❌ Position {position_id} not found in historical positions. Available IDs: {found_position_ids}")
                    else:
                        logger.warning(f"❌ Failed to get historical positions: {result}")
                except Exception as e:
                    logger.error(f"❌ Failed to get historical position data: {e}")
                    import traceback
                    logger.error(f"Traceback: {traceback.format_exc()}")
            
            # Fallback: Get recent trades to find the closing transaction
            logger.debug(f"🔄 Fallback: Getting trade transactions for {symbol}")
            result = await self.api.get_order_transactions_by_symbol(
                symbol=mexc_symbol, 
                page_size=50  # Get more trades to find the close
            )
            
            logger.debug(f"📊 Trade transactions API response: success={result.success}, data_count={len(result.data) if result.data else 0}")
            
            if result.success and result.data:
                # Quiet raw trade dumps; no verbose printing
                # Look for CLOSE transactions (side=4)
                close_trades = []
                for transaction in result.data:
                    if hasattr(transaction, 'side') and transaction.side == 4:  # CLOSE
                        close_trades.append(transaction)
                    elif isinstance(transaction, dict) and transaction.get('side') == 4:
                        close_trades.append(transaction)
                
                logger.debug(f"📊 Found {len(close_trades)} CLOSE transactions")
                
                if close_trades:
                    # Get the most recent close trade
                    latest_close = close_trades[0]
                    
                    # Extract data
                    if hasattr(latest_close, 'price'):
                        # Object format
                        close_data = {
                            'exit_price': float(latest_close.price),
                            'exit_time': datetime.fromtimestamp(latest_close.time / 1000) if latest_close.time else None,
                            'total_pnl_usd': float(getattr(latest_close, 'pnl', 0)),
                            'total_fees': float(latest_close.fee),
                            'exit_quantity': float(latest_close.vol),
                            'order_id': getattr(latest_close, 'orderId', getattr(latest_close, 'order_id', ''))
                        }
                    else:
                        # Dict format
                        close_data = {
                            'exit_price': float(latest_close.get('price', 0)),
                            'exit_time': datetime.fromtimestamp(latest_close.get('time', 0) / 1000) if latest_close.get('time') else None,
                            'total_pnl_usd': float(latest_close.get('pnl', 0)),
                            'total_fees': float(latest_close.get('fee', 0)),
                            'exit_quantity': float(latest_close.get('vol', 0)),
                            'order_id': latest_close.get('orderId', latest_close.get('order_id', ''))
                        }
                    
                    logger.debug(f"📊 Extracted trade close data: {close_data}")
                    return close_data
                else:
                    logger.debug(f"❌ No CLOSE transactions found for {symbol}")
                    return {}
            else:
                logger.debug(f"❌ Failed to get trades for {symbol}: {result}")
                return {}
                
        except Exception as e:
            logger.error(f"Error getting position close data for {symbol}: {e}")
            return {}

    async def get_trigger_orders(self, symbol: Optional[str] = None, states: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get trigger orders (TP/SL orders) from MEXC"""
        if not self._connected or not self.api:
            return []

        try:
            # Get trigger orders
            result = await self.api.get_trigger_orders(
                symbol=symbol,
                states=states,
                page_size=50  # Get more to find relevant orders
            )

            if result.success and result.data:
                trigger_orders = []
                for trigger in result.data:
                    # Handle both dict and TriggerOrder object responses
                    if hasattr(trigger, 'id'):
                        # TriggerOrder object
                        trigger_data = {
                            'id': trigger.id,
                            'symbol': trigger.symbol,
                            'side': trigger.side,
                            'trigger_price': float(trigger.triggerPrice),
                            'price': float(trigger.price),
                            'quantity': float(trigger.vol),
                            'state': trigger.state,
                            'order_id': getattr(trigger, 'orderId', None),  # This is the executed order ID!
                            'create_time': trigger.createTime,
                            'update_time': trigger.updateTime,
                            'trigger_type': trigger.triggerType
                        }
                    else:
                        # Dictionary response
                        trigger_data = {
                            'id': trigger.get('id', ''),
                            'symbol': trigger.get('symbol', ''),
                            'side': trigger.get('side', ''),
                            'trigger_price': float(trigger.get('triggerPrice', 0)),
                            'price': float(trigger.get('price', 0)),
                            'quantity': float(trigger.get('vol', 0)),
                            'state': trigger.get('state', ''),
                            'order_id': trigger.get('orderId'),  # This is the executed order ID!
                            'create_time': trigger.get('createTime', 0),
                            'update_time': trigger.get('updateTime', 0),
                            'trigger_type': trigger.get('triggerType', '')
                        }
                    trigger_orders.append(trigger_data)
                return trigger_orders
            else:
                logger.warning(f"Failed to get trigger orders: {result}")
                return []

        except Exception as e:
            logger.error(f"Error getting trigger orders: {e}")
            return []
    
    async def get_stop_limit_order_id(self, order_id: str) -> Optional[int]:
        """Get the stop limit order ID for a given order ID"""
        try:
            # Get all stop limit orders
            stop_orders = await self.api.get_stop_limit_orders()
            
            logger.info(f"🔍 Searching for stop limit order with orderId: {order_id}")
            logger.info(f"🔍 Found {len(stop_orders.data) if stop_orders.data else 0} stop limit orders")
            
            if stop_orders.data:
                for stop_order in stop_orders.data:
                    logger.info(f"🔍 Checking stop order: orderId={stop_order.get('orderId')}, state={stop_order.get('state')}, id={stop_order.get('id')}")
                    if stop_order.get('orderId') == order_id and stop_order.get('state') == 1:  # Active state
                        stop_order_id = stop_order.get('id')
                        logger.info(f"🔧 Found stop limit order ID: {stop_order_id} for order {order_id}")
                        return stop_order_id
            
            logger.warning(f"⚠️ No active stop limit order found for order {order_id}")
            return None
            
        except Exception as e:
            logger.error(f"Error getting stop limit order ID: {e}")
            return None

    async def modify_attached_sl_tp(self, order_id: str, stop_loss_price: Optional[float] = None, take_profit_price: Optional[float] = None) -> Dict[str, Any]:
        """Modify the attached stop loss and/or take profit prices for an order"""
        try:
            # First, get the stop limit order ID
            stop_order_id = await self.get_stop_limit_order_id(order_id)
            
            if stop_order_id:
                # Use the correct method with stop limit order ID
                response = await self.api.update_stop_limit_trigger_plan_price(
                    stop_plan_order_id=stop_order_id,
                    stop_loss_price=stop_loss_price,
                    take_profit_price=take_profit_price
                )
            else:
                # Fallback to original method (may not work)
                broker_order_id = int(order_id)
                response = await self.api.change_stop_limit_trigger_price(
                    order_id=broker_order_id,
                    stop_loss_price=stop_loss_price,
                    take_profit_price=take_profit_price
                )
            
            if response.success:
                logger.info(f"✅ Successfully modified attached SL/TP for order {order_id}")
                return {
                    'success': True,
                    'message': 'SL/TP prices updated successfully',
                    'stop_order_id': stop_order_id
                }
            else:
                logger.error(f"❌ Failed to modify attached SL/TP: {response.message}")
                return {
                    'success': False,
                    'error': response.message
                }
                
        except Exception as e:
            logger.error(f"Error modifying attached SL/TP: {e}")
            return {
                'success': False,
                'error': str(e)
            }

    async def change_take_profit_price(self, order_id: str, new_price: float) -> Dict[str, Any]:
        """Change the take profit price for an order"""
        try:
            # First, get the stop limit order ID
            stop_order_id = await self.get_stop_limit_order_id(order_id)
            
            if stop_order_id:
                # Use the correct method with stop limit order ID
                response = await self.api.update_stop_limit_trigger_plan_price(
                    stop_plan_order_id=stop_order_id,
                    take_profit_price=new_price
                )
            else:
                # Fallback to original method (may not work)
                broker_order_id = int(order_id)
                response = await self.api.change_stop_limit_trigger_price(
                    order_id=broker_order_id,
                    take_profit_price=new_price
                )
            
            if response.success:
                logger.info(f"✅ Successfully changed TP price to {new_price} for order {order_id}")
                return {
                    'success': True,
                    'message': f'TP price updated to {new_price}',
                    'stop_order_id': stop_order_id
                }
            else:
                logger.error(f"❌ Failed to change TP price: {response.message}")
                return {
                    'success': False,
                    'error': response.message
                }
                
        except Exception as e:
            logger.error(f"Error changing TP price: {e}")
            return {
                'success': False,
                'error': str(e)
            }

    async def change_stop_loss_price(self, order_id: str, new_price: float) -> Dict[str, Any]:
        """Change the stop loss price for an order"""
        try:
            # First, get the stop limit order ID
            stop_order_id = await self.get_stop_limit_order_id(order_id)
            
            if stop_order_id:
                # Use the correct method with stop limit order ID
                response = await self.api.update_stop_limit_trigger_plan_price(
                    stop_plan_order_id=stop_order_id,
                    stop_loss_price=new_price
                )
            else:
                # Fallback to original method (may not work)
                broker_order_id = int(order_id)
                response = await self.api.change_stop_limit_trigger_price(
                    order_id=broker_order_id,
                    stop_loss_price=new_price
                )
            
            if response.success:
                logger.info(f"✅ Successfully changed SL price to {new_price} for order {order_id}")
                return {
                    'success': True,
                    'message': f'SL price updated to {new_price}',
                    'stop_order_id': stop_order_id
                }
            else:
                logger.error(f"❌ Failed to change SL price: {response.message}")
                return {
                    'success': False,
                    'error': response.message
                }
                
        except Exception as e:
            logger.error(f"Error changing SL price: {e}")
            return {
                'success': False,
                'error': str(e)
            }
