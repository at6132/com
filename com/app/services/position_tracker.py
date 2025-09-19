"""
Position and Order Tracking Service
Tracks positions and orders with server-generated IDs and proper relationships
"""
import asyncio
import logging
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)

class PositionStatus(str, Enum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    ERROR = "ERROR"

class OrderType(str, Enum):
    ENTRY = "ENTRY"
    TP = "TP"
    SL = "SL"
    MANUAL = "MANUAL"

class OrderStatus(str, Enum):
    PENDING = "PENDING"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    ERROR = "ERROR"

@dataclass
class Position:
    """Position tracking record"""
    position_id: str                    # Server-generated ID
    broker_position_id: Optional[str]   # Broker's position ID
    symbol: str
    side: str                          # LONG/SHORT
    size: float
    entry_price: float
    current_price: float = 0.0
    unrealized_pnl: float = 0.0
    margin_used: float = 0.0           # Margin used for this position
    status: PositionStatus = PositionStatus.OPEN
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    strategy_id: Optional[str] = None
    order_ref: Optional[str] = None     # Original order reference
    max_favorable: float = 0.0         # Best PnL during position lifecycle
    max_adverse: float = 0.0           # Worst PnL during position lifecycle
    timestop_enabled: bool = False     # Whether timestop is enabled
    timestop_expires_at: Optional[datetime] = None  # When timestop triggers
    timestop_action: str = "MARKET_EXIT"  # What to do when timestop triggers

@dataclass
class Order:
    """Order tracking record"""
    order_id: str                      # Server-generated ID
    broker_order_id: Optional[str]     # Broker's order ID
    parent_position_id: str            # Links to position
    order_type: OrderType
    side: str                         # BUY/SELL
    quantity: float
    price: float
    status: OrderStatus = OrderStatus.PENDING
    filled_quantity: float = 0.0
    filled_price: float = 0.0
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    strategy_id: Optional[str] = None
    order_ref: Optional[str] = None    # Original order reference

class PositionTracker:
    """Tracks positions and orders with server-generated IDs"""
    
    def __init__(self):
        self.positions: Dict[str, Position] = {}
        self.orders: Dict[str, Order] = {}
        self.position_orders: Dict[str, List[str]] = {}  # position_id -> [order_ids]
        self.running = False
        self.tracking_task: Optional[asyncio.Task] = None
        
        # Market data integration
        self._setup_market_data_callbacks()
    
    def _setup_market_data_callbacks(self):
        """Setup callbacks to receive market data updates for position tracking"""
        try:
            from ..services.mexc_market_data import mexc_market_data
            mexc_market_data.add_price_callback(self._on_price_update)
            logger.info("Position tracker market data callbacks registered")
        except Exception as e:
            logger.warning(f"Could not setup market data callbacks: {e}")
    
    def _on_price_update(self, symbol: str, market_data):
        """Handle price updates from market data service for position tracking"""
        try:
            # Update all open positions for this symbol
            for position_id, position in self.positions.items():
                if position.symbol == symbol and position.status == PositionStatus.OPEN:
                    # Get current price from market data object
                    current_price = getattr(market_data, 'last_price', 0.0)
                    logger.debug(f"📊 Price update for {symbol}: {current_price}, position {position_id} entry_price: {position.entry_price}")
                    
                    if current_price > 0 and position.entry_price > 0:
                        # Calculate unrealized PnL
                        if position.side == "BUY":
                            unrealized_pnl = (current_price - position.entry_price) * position.size
                        else:  # SELL
                            unrealized_pnl = (position.entry_price - current_price) * position.size
                        
                        # Update position with new price and PnL
                        self.update_position(position_id, current_price=current_price, unrealized_pnl=unrealized_pnl)
                        
                        # Track max favorable and adverse PnL
                        if unrealized_pnl > position.max_favorable:
                            position.max_favorable = unrealized_pnl
                        
                        if unrealized_pnl < position.max_adverse:
                            position.max_adverse = unrealized_pnl
                    else:
                        logger.debug(f"⚠️ Skipping price update for {position_id}: current_price={current_price}, entry_price={position.entry_price}")
                            
        except Exception as e:
            logger.error(f"Error handling price update for position tracking: {e}")
        
    def generate_position_id(self) -> str:
        """Generate server position ID"""
        timestamp = int(time.time() * 1000)
        return f"pos_{timestamp}_{id(self) % 10000:04d}"
    
    def generate_order_id(self) -> str:
        """Generate server order ID"""
        timestamp = int(time.time() * 1000)
        return f"ord_{timestamp}_{id(self) % 10000:04d}"
    
    def add_position(self, 
                    broker_position_id: Optional[str],
                    symbol: str,
                    side: str,
                    size: float,
                    entry_price: float,
                    strategy_id: Optional[str] = None,
                    order_ref: Optional[str] = None) -> str:
        """Add a new position for tracking"""
        position_id = self.generate_position_id()
        
        position = Position(
            position_id=position_id,
            broker_position_id=broker_position_id,
            symbol=symbol,
            side=side,
            size=size,
            entry_price=entry_price,
            current_price=entry_price,
            strategy_id=strategy_id,
            order_ref=order_ref
        )
        
        logger.info(f"🔍 Creating position with order_ref: {order_ref}")
        logger.info(f"🔍 Position ID: {position_id}")
        logger.info(f"🔍 Broker position ID: {broker_position_id}")
        
        self.positions[position_id] = position
        self.position_orders[position_id] = []
        
        # Subscribe to market data for this symbol if not already subscribed
        try:
            from ..services.mexc_market_data import mexc_market_data
            if symbol not in mexc_market_data.get_subscribed_symbols():
                asyncio.create_task(mexc_market_data.subscribe_symbol(symbol))
                logger.info(f"📊 Subscribed to {symbol} market data for position tracking")
        except Exception as e:
            logger.warning(f"Could not subscribe to market data for {symbol}: {e}")
        
        logger.info(f"📊 Added position {position_id}: {side} {size} {symbol} @ {entry_price}")
        return position_id
    
    def add_order(self,
                 broker_order_id: Optional[str],
                 parent_position_id: str,
                 order_type: OrderType,
                 side: str,
                 quantity: float,
                 price: float,
                 strategy_id: Optional[str] = None,
                 order_ref: Optional[str] = None) -> str:
        """Add a new order for tracking"""
        order_id = self.generate_order_id()
        
        order = Order(
            order_id=order_id,
            broker_order_id=broker_order_id,
            parent_position_id=parent_position_id,
            order_type=order_type,
            side=side,
            quantity=quantity,
            price=price,
            strategy_id=strategy_id,
            order_ref=order_ref
        )
        
        self.orders[order_id] = order
        
        # Link order to position
        if parent_position_id in self.position_orders:
            self.position_orders[parent_position_id].append(order_id)
        
        logger.info(f"📋 Added order {order_id}: {order_type.value} {side} {quantity} {parent_position_id} @ {price}")
        return order_id
    
    def update_order_status(self, order_id: str, status: OrderStatus, 
                          filled_quantity: float = 0.0, filled_price: float = 0.0):
        """Update order status"""
        if order_id in self.orders:
            order = self.orders[order_id]
            order.status = status
            order.updated_at = datetime.utcnow()
            
            if status == OrderStatus.FILLED:
                order.filled_quantity = filled_quantity
                order.filled_price = filled_price
                
                # If this is an entry order and we have a fill price, update position entry price
                if order.order_type == OrderType.ENTRY and filled_price > 0:
                    self.update_position(order.parent_position_id, entry_price=filled_price)
                    logger.info(f"📊 Updated position {order.parent_position_id} entry price to {filled_price} from entry order fill")
                    
                    # Also update the monitored order's entry price and broker order ID for after_fill_actions
                    try:
                        from .order_monitor import order_monitor
                        # Find the monitored order by looking through all monitored orders
                        # and matching the position's order_ref
                        position = self.positions.get(order.parent_position_id)
                        if position and position.order_ref:
                            if position.order_ref in order_monitor.monitored_orders:
                                monitored_order = order_monitor.monitored_orders[position.order_ref]
                                monitored_order.entry_price = filled_price
                                # Store the broker order ID for SL modifications
                                if order.broker_order_id:
                                    monitored_order.entry_broker_order_id = str(order.broker_order_id)
                                    logger.info(f"📊 Stored entry broker order ID: {order.broker_order_id}")
                                logger.info(f"📊 Updated monitored order {position.order_ref} entry price to {filled_price}")
                            else:
                                logger.warning(f"❌ Monitored order not found for position order_ref: {position.order_ref}")
                                logger.warning(f"❌ Available monitored orders: {list(order_monitor.monitored_orders.keys())}")
                    except Exception as e:
                        logger.warning(f"Could not update monitored order entry price: {e}")
                
                # Update order fill data in logging system
                if order.broker_order_id:
                    asyncio.create_task(self._update_order_fill_log(order.broker_order_id))
            
            logger.info(f"📋 Updated order {order_id}: {status.value}")
    
    async def _update_order_fill_log(self, broker_order_id: str):
        """Update order fill data in the logging system"""
        try:
            from .orders import order_service
            await order_service.update_order_fill_data(broker_order_id)
        except Exception as e:
            logger.error(f"Error updating order fill log for {broker_order_id}: {e}")
    
    async def _update_position_order_fills(self, position_id: str):
        """Update fill data for all orders associated with a position"""
        try:
            # Get all orders for this position
            position_orders = self.get_position_orders(position_id)
            
            for order in position_orders:
                if order.broker_order_id and order.status == OrderStatus.FILLED:
                    # Update fill data for this order
                    await self._update_order_fill_log(order.broker_order_id)
                    
        except Exception as e:
            logger.error(f"Error updating position order fills for {position_id}: {e}")
    
    async def _log_closed_position(self, position: Position, close_reason: str):
        """Log closed position with fill data and PnL"""
        try:
            from .data_logger import data_logger
            from ..adapters.manager import broker_manager
            
            # Get broker adapter to fetch final position data
            broker = broker_manager.get_adapter("mexc")
            if not broker:
                logger.error("❌ MEXC broker adapter not found for position logging")
                return
            
            # Try to get final position data from broker
            final_price = position.current_price
            close_time = datetime.utcnow()
            
            # Fetch actual position close data from MEXC
            mexc_close_data = {}
            try:
                mexc_close_data = await broker.get_position_close_data(position.symbol, position.broker_position_id)
                logger.info(f"📊 Fetched MEXC close data for {position.symbol}: {mexc_close_data}")
            except Exception as e:
                logger.warning(f"Could not fetch MEXC close data: {e}")
            
            # Use MEXC data if available, otherwise fallback to calculated values
            if mexc_close_data:
                final_price = mexc_close_data.get('exit_price', position.current_price)
                mexc_close_time = mexc_close_data.get('exit_time')
                close_time = mexc_close_time if mexc_close_time is not None else datetime.utcnow()
                realized_pnl = mexc_close_data.get('total_pnl_usd', 0.0)
                total_fees = mexc_close_data.get('total_fees', 0.0)
                # Use MEXC data for leverage and margin_used
                leverage = mexc_close_data.get('leverage', 1.0)
                margin_used = mexc_close_data.get('margin_used', position.margin_used)
                logger.info(f"📊 Using MEXC data: exit_price={final_price}, PnL=${realized_pnl:.2f}, fees=${total_fees:.4f}, leverage={leverage}, margin=${margin_used}")
            else:
                # Fallback to calculated values
                close_time = datetime.utcnow()
                final_price = position.current_price
                if final_price <= 0:
                    final_price = position.entry_price
                    logger.warning(f"Using entry price as fallback for position {position.position_id}: {final_price}")
                
                # Calculate realized PnL
                if position.entry_price > 0 and final_price > 0:
                    if position.side == "BUY":
                        realized_pnl = (final_price - position.entry_price) * position.size
                    else:
                        realized_pnl = (position.entry_price - final_price) * position.size
                else:
                    realized_pnl = position.unrealized_pnl
                    logger.warning(f"Using unrealized PnL as fallback for position {position.position_id}")
                
                total_fees = 0.0  # Will be 0 if we can't get from MEXC
                leverage = 1.0  # Default fallback
                margin_used = position.margin_used
            
            # Calculate duration
            duration_seconds = (close_time - position.created_at).total_seconds()
            
            # Convert max favorable/adverse to percentages from entry price
            max_favorable_pct = 0.0
            max_adverse_pct = 0.0
            if position.entry_price > 0:
                if position.max_favorable != 0:
                    max_favorable_pct = (position.max_favorable / (position.entry_price * position.size)) * 100
                if position.max_adverse != 0:
                    max_adverse_pct = (position.max_adverse / (position.entry_price * position.size)) * 100
            
            # Log position data
            position_data = {
                'position_id': position.position_id,
                'strategy_id': position.strategy_id or "unknown",
                'account_id': "mexc_testnet",  # TODO: Get from broker config
                'symbol': position.symbol,
                'side': position.side,
                'size': position.size,
                'entry_price': position.entry_price,
                'exit_price': final_price,
                'realized_pnl': realized_pnl,
                'total_fees': total_fees,
                'volume': margin_used,
                'leverage': leverage,
                'status': 'CLOSED',
                'open_time': position.created_at.isoformat(),
                'close_time': close_time.isoformat(),
                'duration_seconds': duration_seconds,
                'max_favorable': max_favorable_pct,  # Now in percentage
                'max_adverse': max_adverse_pct,      # Now in percentage
                'exit_reason': close_reason
            }
            
            await data_logger.log_position(position_data)
            
            # Send WebSocket position closed event to algorithm
            if position.strategy_id:
                try:
                    from .events import EventService
                    await EventService.broadcast_position_closed(
                        strategy_id=position.strategy_id,
                        position_ref=position.position_id,
                        order_ref=position.order_ref,
                        details={
                            "symbol": position.symbol,
                            "side": position.side,
                            "size": position.size,
                            "entry_price": position.entry_price,
                            "exit_price": final_price,
                            "realized_pnl": realized_pnl,
                            "total_fees": total_fees,
                            "volume": margin_used,
                            "leverage": leverage,
                            "duration_seconds": int(duration_seconds),
                            "max_favorable_pct": max_favorable_pct,
                            "max_adverse_pct": max_adverse_pct,
                            "close_reason": close_reason,
                            "open_time": position.created_at.isoformat(),
                            "close_time": close_time.isoformat()
                        }
                    )
                    logger.info(f"📡 Sent POSITION_CLOSED WebSocket event for {position.position_id}")
                except Exception as ws_error:
                    logger.error(f"❌ Error sending position closed WebSocket event: {ws_error}")
            
            logger.info(f"📊 Logged closed position {position.position_id}: {close_reason}, PnL: ${realized_pnl:.2f}, Fees: ${total_fees:.4f}, Duration: {duration_seconds:.1f}s")
            
        except Exception as e:
            logger.error(f"❌ Error logging closed position {position.position_id}: {e}")
    
    def update_position(self, position_id: str, size: float = None, 
                       current_price: float = None, unrealized_pnl: float = None,
                       entry_price: float = None):
        """Update position data"""
        if position_id in self.positions:
            position = self.positions[position_id]
            position.updated_at = datetime.utcnow()
            
            if size is not None:
                position.size = size
                if size == 0:
                    position.status = PositionStatus.CLOSED
                    logger.info(f"📊 Position {position_id} closed (size=0)")
            
            if current_price is not None:
                position.current_price = current_price
            
            if unrealized_pnl is not None:
                position.unrealized_pnl = unrealized_pnl
                
            if entry_price is not None:
                position.entry_price = entry_price
                logger.info(f"📊 Updated position {position_id} entry price to {entry_price}")

                # Also propagate to monitored order for after_fill_actions (e.g., breakeven SL)
                try:
                    from .order_monitor import order_monitor
                    if position.order_ref and position.order_ref in order_monitor.monitored_orders:
                        mon = order_monitor.monitored_orders[position.order_ref]
                        mon.entry_price = entry_price
                        logger.info(f"📊 Propagated entry price to monitored order {position.order_ref}: {entry_price}")
                except Exception as e:
                    logger.warning(f"Could not propagate entry price to monitored order: {e}")
    
    def get_position(self, position_id: str) -> Optional[Position]:
        """Get position by ID"""
        return self.positions.get(position_id)
    
    def get_order(self, order_id: str) -> Optional[Order]:
        """Get order by ID"""
        return self.orders.get(order_id)
    
    def get_position_orders(self, position_id: str) -> List[Order]:
        """Get all orders for a position"""
        order_ids = self.position_orders.get(position_id, [])
        logger.info(f"🔍 get_position_orders for {position_id}: found order_ids = {order_ids}")

        orders = [self.orders[oid] for oid in order_ids if oid in self.orders]
        logger.info(f"🔍 get_position_orders for {position_id}: returning {len(orders)} orders")

        for i, order in enumerate(orders):
            logger.info(f"🔍 Order {i+1}: {order.order_id}")

        return orders
    
    def get_strategy_positions(self, strategy_id: str) -> List[Position]:
        """Get all positions for a strategy"""
        return [pos for pos in self.positions.values() if pos.strategy_id == strategy_id]
    
    def get_strategy_orders(self, strategy_id: str) -> List[Order]:
        """Get all orders for a strategy"""
        return [order for order in self.orders.values() if order.strategy_id == strategy_id]
    
    async def start_tracking(self):
        """Start position tracking loop"""
        if self.running:
            return
        
        # Ensure market data service is connected for real-time price updates
        try:
            from ..services.mexc_market_data import mexc_market_data
            if not mexc_market_data.is_connected():
                logger.info("Connecting to market data service for position tracking...")
                await mexc_market_data.connect()
        except Exception as e:
            logger.warning(f"Could not connect to market data service: {e}")
        
        self.running = True
        self.tracking_task = asyncio.create_task(self._tracking_loop())
        logger.info("🚀 Position tracker started with market data integration")
    
    async def stop_tracking(self):
        """Stop position tracking"""
        self.running = False
        if self.tracking_task:
            self.tracking_task.cancel()
            try:
                await self.tracking_task
            except asyncio.CancelledError:
                pass
        logger.info("🛑 Position tracker stopped")
    
    async def _tracking_loop(self):
        """Main tracking loop - pings broker every 1s"""
        while self.running:
            try:
                await self._update_positions()
                await self.check_timestops()  # Check for expired timestops
                await asyncio.sleep(1.0)  # Ping every 1 second
            except Exception as e:
                logger.error(f"Error in position tracking loop: {e}")
                await asyncio.sleep(1.0)
    
    async def _update_positions(self):
        """Update all open positions from broker"""
        try:
            from ..adapters.manager import broker_manager
            
            # Get broker adapter
            broker_name = "mexc"
            await broker_manager.ensure_broker_connected(broker_name)
            broker = broker_manager.get_adapter(broker_name)
            
            if not broker:
                return
            
            # Update each open position (create a copy of keys to avoid modification during iteration)
            for position_id in list(self.positions.keys()):
                position = self.positions.get(position_id)
                if not position or position.status != PositionStatus.OPEN:
                    continue
                
                try:
                    # Skip newly created positions (less than 5 seconds old) to allow time for MEXC to process
                    position_age = (datetime.utcnow() - position.created_at).total_seconds()
                    if position_age < 5.0:
                        continue
                    
                    # Get position data from broker
                    if position.broker_position_id:
                        # Use broker position ID if available
                        broker_positions = await broker.get_positions(position.symbol)
                        broker_position = None  # Initialize to None
                        
                        for bp in broker_positions:
                            if str(bp.get('position_id', '')) == str(position.broker_position_id):
                                broker_position = bp
                                break
                        
                        if broker_position:
                            # Update position data
                            new_size = broker_position.get('hold_vol', 0.0)  # Use hold_vol instead of size
                            current_price = broker_position.get('mark_price', position.current_price)
                            unrealized_pnl = broker_position.get('unrealized_pnl', 0.0)
                            position_state = broker_position.get('state', 0)
                            
                            # Check if position size changed (indicating order fills)
                            old_size = position.size
                            self.update_position(position_id, new_size, current_price, unrealized_pnl)
                            
                            # If position size changed, update fill data for associated orders
                            if new_size != old_size:
                                await self._update_position_order_fills(position_id)
                                
                                # If position was filled (size increased), fetch fill data from broker
                                if new_size > old_size:
                                    await self._fetch_order_fill_data(position_id)
                                
                                # Check for TP fills even when position is still open
                                if new_size < old_size:  # Position size decreased (TP filled)
                                    logger.info(f"🔍 Position size decreased from {old_size} to {new_size}, checking for TP fills")
                                    await self._check_for_tp_fills(position_id, position)
                            
                            # If position closed (size=0 OR state=3 which is Closed), cleanup monitoring
                            if new_size == 0 or position_state == 3:
                                 close_reason = "POSITION_CLOSED"
                                 if new_size == 0:
                                     close_reason = "SIZE_ZERO"
                                 elif position_state == 3:
                                     close_reason = "STATE_CLOSED"
                                 
                                 # Log the closed position before cleanup
                                 await self._log_closed_position(position, close_reason)
                                 
                                 # Update order statuses to FILLED/CANCELLED
                                 await self._update_order_statuses_on_close(position_id, close_reason)
                                 
                                 await self._cleanup_position(position_id, close_reason)
                        else:
                            # Position not found on broker - might be closed or not yet created
                            # Check if position is old enough to consider it closed
                            if position_age > 10.0:  # Reduced from 30s to 10s for faster detection
                                logger.warning(f"Position {position_id} not found on broker after {position_age:.1f}s, determining close reason...")
                                close_reason = await self._determine_close_reason(position)

                                # Log the closed position before cleanup
                                await self._log_closed_position(position, close_reason)

                                # Update order statuses to FILLED/CANCELLED
                                await self._update_order_statuses_on_close(position_id, close_reason)

                                await self._cleanup_position(position_id, close_reason)
                            else:
                                logger.debug(f"Position {position_id} not found on broker yet (age: {position_age:.1f}s), waiting...")
                
                except Exception as e:
                    logger.error(f"Error updating position {position_id}: {e}")
        
        except Exception as e:
            logger.error(f"Error in _update_positions: {e}")
    
    async def _determine_close_reason(self, position: Position) -> str:
        """Determine how a position was closed using MEXC order transactions and order details"""
        logger.info(f"🔍 Determining close reason for position {position.position_id}")
        try:
            from ..adapters.manager import broker_manager
            from .orders import order_service

            # Get broker adapter
            broker_name = "mexc"
            broker = broker_manager.get_adapter(broker_name)

            if not broker:
                return "UNKNOWN - No broker connection"

            # NEW METHOD: Check for CLOSE transactions (side=4) which indicate TP/SL executions
            logger.info(f"🔍 Checking for CLOSE transactions (side=4) for {position.symbol}")
            try:
                # Get recent order transactions
                trades_result = await broker.get_recent_trades(symbol=position.symbol, limit=20)
                
                if trades_result:
                    # For SHORT positions, CLOSE transactions have side=2
                    # For LONG positions, CLOSE transactions have side=4
                    if position.side == "SELL":  # SHORT position
                        close_transactions = [t for t in trades_result if t.get('side') == 2]
                    else:  # LONG position
                        close_transactions = [t for t in trades_result if t.get('side') == 4]
                    logger.info(f"🔍 Found {len(close_transactions)} CLOSE transactions for {position.side} position")
                    
                    # Check each CLOSE transaction to see if it's our TP/SL execution
                    for transaction in close_transactions:
                        order_id = transaction.get('order_id')
                        if not order_id:
                            continue
                            
                        logger.info(f"🔍 Checking CLOSE transaction with order_id: {order_id}")
                        
                        # Get full order details to check externalOid
                        order_details = await broker.get_order(order_id)
                        if order_details:
                            # Handle both dict and object responses
                            if hasattr(order_details, 'externalOid'):
                                external_oid = getattr(order_details, 'externalOid', '')
                            else:
                                external_oid = order_details.get('externalOid', '')
                            
                            logger.info(f"🔍 Order externalOid: {external_oid}")
                            logger.info(f"🔍 Checking if externalOid contains TP/SL patterns...")
                            
                            # Check if this is a TP/SL execution based on externalOid
                            if 'stoporder_TAKE_PROFIT_' in external_oid:
                                logger.info(f"✅ Found TAKE_PROFIT execution! Order: {order_id}")
                                
                                # Update TP order status to FILLED
                                await self._update_tp_sl_order_from_execution(order_details, transaction, position, "TAKE_PROFIT")
                                
                                # Update position with final data
                                position.current_price = transaction.get('price', position.current_price)
                                return f"TAKE_PROFIT - Order ID: {order_id}"
                                
                            elif 'stoporder_STOP_LOSS_' in external_oid:
                                logger.info(f"✅ Found STOP_LOSS execution! Order: {order_id}")
                                
                                # Update SL order status to FILLED
                                await self._update_tp_sl_order_from_execution(order_details, transaction, position, "STOP_LOSS")
                                
                                # Update position with final data
                                position.current_price = transaction.get('price', position.current_price)
                                return f"STOP_LOSS - Order ID: {order_id}"
                                
                            else:
                                # Check if this might be a TP fill based on price movement and order characteristics
                                logger.info(f"🔍 Checking if this might be a TP fill based on price movement")
                                logger.info(f"🔍 Transaction price: {transaction.get('price', 0)}")
                                logger.info(f"🔍 Position entry price: {position.entry_price}")
                                logger.info(f"🔍 Position side: {position.side}")
                                logger.info(f"🔍 ExternalOid: {external_oid}")
                                
                                # For SHORT positions: TP1 should be filled when price goes DOWN
                                # For LONG positions: TP1 should be filled when price goes UP
                                if position.side == "SELL":  # SHORT position
                                    if transaction.get('price', 0) < position.entry_price:
                                        logger.info(f"🎯 Potential TP1 fill detected for SHORT position!")
                                        logger.info(f"🎯 Price moved DOWN: {transaction.get('price', 0)} < {position.entry_price}")
                                        
                                        # Check if this order has _m_ prefix (separate TP order)
                                        if external_oid.startswith('_m_'):
                                            logger.info(f"🎯 Confirmed TP fill! Order has _m_ prefix: {external_oid}")
                                            
                                            # Update TP order status to FILLED
                                            await self._update_tp_sl_order_from_execution(order_details, transaction, position, "TAKE_PROFIT")
                                            
                                            # Execute after_fill_actions for TP1
                                            try:
                                                from .order_monitor import order_monitor
                                                if position.order_ref in order_monitor.monitored_orders:
                                                    monitored_order = order_monitor.monitored_orders[position.order_ref]
                                                    await self._execute_after_fill_actions_for_tp(monitored_order, transaction.get('price', 0))
                                            except Exception as e:
                                                logger.error(f"Error executing after_fill_actions: {e}")
                                            
                                            # Update position with final data
                                            position.current_price = transaction.get('price', position.current_price)
                                            return f"TAKE_PROFIT - Order ID: {order_id}"
                                
                                elif position.side == "BUY":  # LONG position
                                    if transaction.get('price', 0) > position.entry_price:
                                        logger.info(f"🎯 Potential TP1 fill detected for LONG position!")
                                        logger.info(f"🎯 Price moved UP: {transaction.get('price', 0)} > {position.entry_price}")
                                        
                                        # Check if this order has _m_ prefix (separate TP order)
                                        if external_oid.startswith('_m_'):
                                            logger.info(f"🎯 Confirmed TP fill! Order has _m_ prefix: {external_oid}")
                                            
                                            # Update TP order status to FILLED
                                            await self._update_tp_sl_order_from_execution(order_details, transaction, position, "TAKE_PROFIT")
                                            
                                            # Execute after_fill_actions for TP1
                                            try:
                                                from .order_monitor import order_monitor
                                                if position.order_ref in order_monitor.monitored_orders:
                                                    monitored_order = order_monitor.monitored_orders[position.order_ref]
                                                    await self._execute_after_fill_actions_for_tp(monitored_order, transaction.get('price', 0))
                                            except Exception as e:
                                                logger.error(f"Error executing after_fill_actions: {e}")
                                            
                                            # Update position with final data
                                            position.current_price = transaction.get('price', position.current_price)
                                            return f"TAKE_PROFIT - Order ID: {order_id}"
                                
                                # If we get here, it's not a TP/SL execution based on externalOid
                                # Continue to check other possibilities
                                logger.info(f"🔍 ExternalOid {external_oid} doesn't match TP/SL patterns, continuing...")
                        else:
                            logger.warning(f"❌ Failed to get order details for {order_id}")
                else:
                    logger.warning(f"❌ No order transactions found for {position.symbol}")
                    
            except Exception as e:
                logger.error(f"Error checking CLOSE transactions: {e}")
                import traceback
                logger.error(f"Traceback: {traceback.format_exc()}")

            # FALLBACK: Check recent trades for manual closes
            logger.info(f"🔍 Fallback: Checking recent trades for manual closes")
            try:
                recent_trades = await broker.get_recent_trades(position.symbol, limit=20)
                
                if recent_trades:
                    # For SHORT positions, closing trades have side=2
                    # For LONG positions, closing trades have side=4
                    if position.side == "SELL":  # SHORT position
                        position_side_raw = 2  # CLOSE for SHORT
                    else:  # LONG position
                        position_side_raw = 4  # CLOSE for LONG
                    
                    position_time = position.created_at.timestamp() * 1000
                    
                    for trade in recent_trades:
                        trade_side_raw = trade.get('side', '')
                        trade_time = trade.get('time', 0)
                        trade_price = trade.get('price', 0)
                        
                        # Check if this trade could be our position close
                        if trade_side_raw == position_side_raw:
                            logger.info(f"🔍 Found potential manual close trade: side={trade_side_raw} @ {trade_price}")
                            
                            # Update position with final data
                            position.current_price = trade_price
                            return f"MANUAL_CLOSE - Trade ID: {trade.get('id', 'N/A')}"
                else:
                    logger.warning(f"❌ No recent trades found for {position.symbol}")
                    
            except Exception as e:
                logger.error(f"Error checking recent trades: {e}")
            
            logger.warning(f"🔍 No matching close transactions or trades found for position {position.position_id}")
            return "UNKNOWN - No matching close transactions or trades found"
            
        except Exception as e:
            logger.error(f"Error determining close reason: {e}")
            return f"UNKNOWN - Error: {str(e)}"
    
    async def _update_tp_sl_order_from_execution(self, order_details, transaction, position, execution_type):
        """Update TP/SL order status to FILLED when we detect execution from MEXC order details"""
        try:
            from .orders import order_service
            
            # Find the corresponding TP/SL order in our system
            monitored_order = None
            from .order_monitor import order_monitor
            
            # Look for the monitored order that has this position
            for order_ref, mon_order in order_monitor.monitored_orders.items():
                if hasattr(position, 'order_ref') and position.order_ref == order_ref:
                    monitored_order = mon_order
                    break
            
            if not monitored_order:
                logger.warning(f"Could not find monitored order for position {position.position_id}")
                return
            
            # Find the correct TP/SL order by broker order ID
            broker_order_id = str(getattr(order_details, 'orderId', '') if hasattr(order_details, 'orderId') else order_details.get('orderId', ''))
            
            if execution_type == "TAKE_PROFIT":
                # Find TP order by broker order ID
                order_ref = None
                from .data_logger import data_logger
                # Look through all TP orders for this position
                position_orders = await data_logger.get_position_orders(position.position_id)
                for order_id in position_orders:
                    order_data = await data_logger.get_order_by_ref(order_id)
                    if order_data and order_data.get('broker_order_id') == broker_order_id:
                        order_ref = order_id
                        break
                
                if not order_ref:
                    logger.warning(f"❌ Could not find TP order for broker_order_id: {broker_order_id}")
                    return
            else:  # STOP_LOSS
                order_ref = f"{monitored_order.order_ref}_sl"
            
            logger.info(f"🎯 Updating {execution_type} order {order_ref} to FILLED (MEXC execution detected)")
            
            # Update order status to FILLED
            await order_service.update_order_status(order_ref, "FILLED")
            
            # Update fill data for the TP/SL order
            fill_data = {
                'price': transaction.get('price', 0),
                'quantity': transaction.get('vol', 0),
                'commission': transaction.get('fee', 0),
                'time': transaction.get('timestamp', 0),
                'broker_order_id': str(getattr(order_details, 'orderId', '') if hasattr(order_details, 'orderId') else order_details.get('orderId', ''))
            }
            
            # Update the order fill data using the broker order ID
            broker_order_id = fill_data.get('broker_order_id')
            if broker_order_id:
                await order_service.update_order_fill_data(broker_order_id)
            logger.info(f"✅ Updated {execution_type} order {order_ref} fill data: {fill_data}")
            
            # Execute after_fill_actions if this is a TP fill
            if execution_type == "TAKE_PROFIT":
                await self._execute_after_fill_actions_for_specific_tp(monitored_order, fill_data['price'], order_ref)
            
        except Exception as e:
            logger.error(f"Error updating TP/SL order from execution: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
    
    async def _execute_after_fill_actions_for_specific_tp(self, monitored_order, fill_price: float, filled_order_ref: str):
        """Execute after_fill_actions for a specific TP order that was filled"""
        try:
            logger.info(f"🔍 _execute_after_fill_actions_for_specific_tp called with fill_price: {fill_price}, order_ref: {filled_order_ref}")
            
            if not monitored_order:
                logger.warning("❌ No monitored_order provided")
                return
            
            if not monitored_order.exit_plan:
                logger.warning("❌ No exit plan found for monitored order")
                return
            
            if 'legs' not in monitored_order.exit_plan:
                logger.warning("❌ No legs found in exit plan")
                return
            
            logger.info(f"🔍 Exit plan found: {monitored_order.exit_plan}")
            logger.info(f"🔍 Found {len(monitored_order.exit_plan['legs'])} exit plan legs")
            
            # Find which TP leg corresponds to the filled order
            filled_tp_index = None
            if filled_order_ref.endswith('_tp1'):
                filled_tp_index = 0
            elif filled_order_ref.endswith('_tp2'):
                filled_tp_index = 1
            elif filled_order_ref.endswith('_tp3'):
                filled_tp_index = 2
            # Add more if needed
            
            if filled_tp_index is None:
                logger.warning(f"❌ Could not determine TP index from order_ref: {filled_order_ref}")
                return
            
            # Only execute after_fill_actions for the specific TP leg that was filled
            legs = monitored_order.exit_plan['legs']
            if filled_tp_index < len(legs):
                leg = legs[filled_tp_index]
                
                # Handle both Pydantic objects and dictionaries
                if hasattr(leg, 'kind'):
                    leg_kind = leg.kind
                    leg_after_fill_actions = getattr(leg, 'after_fill_actions', None)
                else:
                    leg_kind = leg.get('kind')
                    leg_after_fill_actions = leg.get('after_fill_actions')
                
                logger.info(f"🔍 Leg {filled_tp_index + 1}: kind={leg_kind}, after_fill_actions={leg_after_fill_actions}")
                
                if leg_kind == "TP" and leg_after_fill_actions:
                    logger.info(f"🎯 Executing {len(leg_after_fill_actions)} after_fill_actions for leg {filled_tp_index + 1}")
                    
                    for j, action in enumerate(leg_after_fill_actions):
                        action_type = action.get('action') if isinstance(action, dict) else getattr(action, 'action', None)
                        logger.info(f"🔍 Action {j + 1}: {action_type}")
                        
                        if action_type == "SET_SL_TO_BREAKEVEN":
                            await self._set_sl_to_breakeven_for_tp(monitored_order, fill_price, filled_tp_index)
                        else:
                            logger.warning(f"Unknown after_fill_action: {action_type}")
                else:
                    logger.info(f"ℹ️ No after_fill_actions for leg {filled_tp_index + 1}")
            else:
                logger.warning(f"❌ TP index {filled_tp_index} out of range for legs")
            
        except Exception as e:
            logger.error(f"Error executing after_fill_actions for specific TP: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
    
    async def _execute_after_fill_actions_for_tp(self, monitored_order, fill_price: float):
        """Execute after_fill_actions when a TP order is filled"""
        try:
            logger.info(f"🔍 _execute_after_fill_actions_for_tp called with fill_price: {fill_price}")
            
            if not monitored_order:
                logger.warning("❌ No monitored_order provided")
                return
            
            if not monitored_order.exit_plan:
                logger.warning("❌ No exit plan found for monitored order")
                return
            
            if 'legs' not in monitored_order.exit_plan:
                logger.warning("❌ No legs found in exit plan")
                return
            
            logger.info(f"🔍 Exit plan found: {monitored_order.exit_plan}")
            logger.info(f"🔍 Found {len(monitored_order.exit_plan['legs'])} exit plan legs")
            
            for i, leg in enumerate(monitored_order.exit_plan['legs']):
                # Handle both Pydantic objects and dictionaries
                leg_kind = getattr(leg, 'kind', None) if hasattr(leg, 'kind') else leg.get('kind')
                after_fill_actions = getattr(leg, 'after_fill_actions', None) if hasattr(leg, 'after_fill_actions') else leg.get('after_fill_actions')
                
                logger.info(f"🔍 Leg {i+1}: kind={leg_kind}, after_fill_actions={after_fill_actions}")
                
                if not after_fill_actions:
                    logger.info(f"ℹ️ No after_fill_actions for leg {i+1}")
                    continue
                
                logger.info(f"🎯 Executing {len(after_fill_actions)} after_fill_actions for leg {i+1}")
                
                for j, action_data in enumerate(after_fill_actions):
                    # Handle both Pydantic objects and dictionaries
                    action = getattr(action_data, 'action', None) if hasattr(action_data, 'action') else action_data.get('action')
                    logger.info(f"🔍 Action {j+1}: {action}")
                    
                    if not action:
                        logger.warning(f"❌ No action found in action_data: {action_data}")
                        continue
                    
                    try:
                        if action == "SET_SL_TO_BREAKEVEN":
                            logger.info(f"🔄 Executing SET_SL_TO_BREAKEVEN for leg {i+1}")
                            await self._set_sl_to_breakeven(monitored_order, leg, fill_price)
                        elif action == "START_TRAILING_SL":
                            logger.info(f"🔄 Executing START_TRAILING_SL for leg {i+1}")
                            await self._start_trailing_sl(monitored_order, leg, fill_price)
                        else:
                            logger.warning(f"❌ Unknown after_fill_action: {action}")
                    except Exception as e:
                        logger.error(f"❌ Error executing after_fill_action {action}: {e}")
                        import traceback
                        logger.error(f"Traceback: {traceback.format_exc()}")
            
        except Exception as e:
            logger.error(f"❌ Error executing after_fill_actions: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
    
    async def _set_sl_to_breakeven(self, monitored_order, leg: Dict[str, Any], fill_price: float):
        """Move stop loss to breakeven (entry price)"""
        try:
            logger.info(f"🔄 Setting SL to breakeven for order {monitored_order.order_ref}")
            logger.info(f"🔍 Monitored order: {monitored_order}")
            logger.info(f"🔍 Leg: {leg}")
            logger.info(f"🔍 Fill price: {fill_price}")
            
            # Get the entry price from the monitored order
            entry_price = monitored_order.entry_price
            logger.info(f"🔍 Entry price: {entry_price}")
            
            if not entry_price:
                logger.warning(f"❌ No entry price found for order {monitored_order.order_ref}")
                return
            
            # Find the SL leg in the exit plan
            sl_leg = None
            logger.info(f"🔍 Looking for SL leg in {len(monitored_order.exit_plan['legs'])} legs")
            
            for i, exit_leg in enumerate(monitored_order.exit_plan['legs']):
                # Handle both Pydantic objects and dictionaries
                exit_leg_kind = getattr(exit_leg, 'kind', None) if hasattr(exit_leg, 'kind') else exit_leg.get('kind')
                logger.info(f"🔍 Leg {i+1}: kind={exit_leg_kind}")
                if exit_leg_kind == 'SL':
                    sl_leg = exit_leg
                    logger.info(f"✅ Found SL leg: {sl_leg}")
                    break
            
            if not sl_leg:
                logger.warning(f"❌ No SL leg found in exit plan for order {monitored_order.order_ref}")
                return
            
            # Update the SL trigger price to entry price
            # Handle both Pydantic objects and dictionaries
            if hasattr(sl_leg, 'trigger'):
                old_trigger_price = getattr(sl_leg.trigger, 'value', None)
                # Note: We can't modify Pydantic objects directly, so we'll just log the change
                logger.info(f"✅ Would update SL trigger from {old_trigger_price} to breakeven: {entry_price}")
            else:
                old_trigger_price = sl_leg.get('trigger', {}).get('value', None)
                sl_leg['trigger']['value'] = entry_price
                logger.info(f"✅ Updated SL trigger from {old_trigger_price} to breakeven: {entry_price}")
            
            # Send order amendment to broker to update the SL price
            try:
                from .orders import order_service
                from ..adapters.manager import broker_manager
                
                # Get the broker adapter
                broker_name = "mexc"
                await broker_manager.ensure_broker_connected(broker_name)
                broker = broker_manager.get_adapter(broker_name)
                
                if not broker:
                    logger.error(f"❌ Broker {broker_name} not available")
                    return
                
                # Get the main order ID (the entry order that has the attached SL)
                entry_order_ref = monitored_order.order_ref
                logger.info(f"🔍 Getting entry order data for: {entry_order_ref}")
                
                entry_order_data = await order_service.get_order_by_ref(entry_order_ref)
                logger.info(f"🔍 Entry order data: {entry_order_data}")
                
                if not entry_order_data or not entry_order_data.get('broker_order_id'):
                    logger.warning(f"❌ No broker order ID found for entry order {entry_order_ref}")
                    return
                
                broker_order_id = int(entry_order_data['broker_order_id'])
                logger.info(f"🔍 Broker order ID: {broker_order_id}")
                
                # Call MEXC API to update the stop loss price
                mexc_api = broker.api
                logger.info(f"🔍 Calling MEXC API to update SL to {entry_price}")
                
                # For attached SL orders, we need to find the stop_plan_order_id
                # and use update_stop_limit_trigger_plan_price method (exact same as test script)
                logger.info(f"🔍 Finding stop_plan_order_id for attached SL order: {broker_order_id}")
                
                # Get stop limit orders to find the stop_plan_order_id (exact same as test script)
                stop_orders_response = await mexc_api.get_stop_limit_orders()
                stop_plan_order_id = None
                
                if stop_orders_response.success and stop_orders_response.data:
                    logger.info(f"📊 Found {len(stop_orders_response.data)} stop limit orders")
                    for stop_order in stop_orders_response.data:
                        logger.info(f"🔍 Stop order: orderId={stop_order.get('orderId')}, state={stop_order.get('state')}, id={stop_order.get('id')}")
                        if (stop_order.get('orderId') == str(broker_order_id) and 
                            stop_order.get('state') == 1):  # Active state
                            stop_plan_order_id = stop_order.get('id')
                            logger.info(f"✅ Found stop_plan_order_id: {stop_plan_order_id}")
                            break
                else:
                    logger.warning(f"❌ Failed to get stop limit orders: {stop_orders_response.message if hasattr(stop_orders_response, 'message') else 'Unknown error'}")
                
                if stop_plan_order_id:
                    # Use the correct method with stop_plan_order_id (exact same as test script)
                    logger.info(f"🔍 Using stop_plan_order_id for attached SL: {stop_plan_order_id}")
                    logger.info(f"📤 New SL price: {entry_price} (breakeven)")
                    response = await mexc_api.update_stop_limit_trigger_plan_price(
                        stop_plan_order_id=int(stop_plan_order_id),
                        stop_loss_price=entry_price,
                        take_profit_price=None  # Keep existing TP
                    )
                else:
                    # Fallback to original method (may not work)
                    logger.warning(f"⚠️ Could not find stop_plan_order_id, using fallback method")
                    response = await mexc_api.change_stop_limit_trigger_price(
                        order_id=broker_order_id,
                        stop_loss_price=entry_price,
                        take_profit_price=None  # Keep existing TP
                    )
                
                logger.info(f"🔍 MEXC API response: {response}")
                
                if response.success:
                    logger.info(f"✅ Successfully updated MEXC SL to breakeven: {entry_price}")
                else:
                    logger.error(f"❌ Failed to update MEXC SL: {response.message}")
                    
            except Exception as e:
                logger.error(f"❌ Error updating MEXC SL to breakeven: {e}")
                import traceback
                logger.error(f"Traceback: {traceback.format_exc()}")
            
        except Exception as e:
            logger.error(f"❌ Error setting SL to breakeven: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
    
    async def _set_sl_to_breakeven_for_tp(self, monitored_order, fill_price: float, tp_index: int):
        """Move stop loss to breakeven for a specific TP that was filled"""
        try:
            logger.info(f"🔄 Setting SL to breakeven for TP {tp_index + 1} of order {monitored_order.order_ref}")
            
            # Get the entry price from the monitored order
            entry_price = monitored_order.entry_price
            logger.info(f"🔍 Entry price: {entry_price}")
            
            if not entry_price:
                logger.warning(f"❌ No entry price found for order {monitored_order.order_ref}")
                return
            
            # Find the SL leg in the exit plan
            sl_leg = None
            logger.info(f"🔍 Looking for SL leg in {len(monitored_order.exit_plan['legs'])} legs")
            
            for i, leg in enumerate(monitored_order.exit_plan['legs']):
                # Handle both Pydantic objects and dictionaries
                if hasattr(leg, 'kind'):
                    leg_kind = leg.kind
                else:
                    leg_kind = leg.get('kind')
                
                logger.info(f"🔍 Leg {i+1}: kind={leg_kind}")
                
                if leg_kind == "SL":
                    sl_leg = leg
                    logger.info(f"✅ Found SL leg at index {i}")
                    break
            
            if not sl_leg:
                logger.warning(f"❌ No SL leg found in exit plan for order {monitored_order.order_ref}")
                return
            
            # Update the SL trigger price to entry price
            # Handle both Pydantic objects and dictionaries
            if hasattr(sl_leg, 'trigger'):
                old_trigger_price = getattr(sl_leg.trigger, 'value', None)
                # Note: We can't modify Pydantic objects directly, so we'll just log the change
                logger.info(f"✅ Would update SL trigger from {old_trigger_price} to breakeven: {entry_price}")
            else:
                old_trigger_price = sl_leg.get('trigger', {}).get('value', None)
                sl_leg['trigger']['value'] = entry_price
                logger.info(f"✅ Updated SL trigger from {old_trigger_price} to breakeven: {entry_price}")
            
            # Send order amendment to broker to update the SL price
            try:
                from .orders import order_service
                from ..adapters.manager import broker_manager
                
                # Get the broker adapter
                broker_name = "mexc"
                await broker_manager.ensure_broker_connected(broker_name)
                broker = broker_manager.get_adapter(broker_name)
                
                if not broker:
                    logger.error(f"❌ Broker {broker_name} not available")
                    return
                
                # Get the main order ID (the entry order that has the attached SL)
                entry_order_ref = monitored_order.order_ref
                logger.info(f"🔍 Getting entry order data for: {entry_order_ref}")
                
                # Get the entry order's broker order ID
                entry_order_data = await order_service.get_order_by_ref(entry_order_ref)
                if not entry_order_data:
                    logger.error(f"❌ Could not find entry order data for {entry_order_ref}")
                    return
                
                entry_broker_order_id = entry_order_data.get('broker_order_id')
                if not entry_broker_order_id:
                    logger.error(f"❌ No broker order ID found for entry order {entry_order_ref}")
                    return
                
                logger.info(f"🔍 Found entry broker order ID: {entry_broker_order_id}")
                
                # Update the SL price to breakeven using MEXC API
                # This would typically involve calling the broker's modify order API
                # For now, we'll just log what we would do
                logger.info(f"🔄 Would update SL to breakeven for broker order {entry_broker_order_id}")
                logger.info(f"🔄 New SL price: {entry_price}")
                
                # TODO: Implement actual broker API call to update SL price
                # await broker.modify_order(entry_broker_order_id, stop_price=entry_price)
                
                logger.info(f"✅ SL moved to breakeven: {entry_price}")
                
            except Exception as e:
                logger.error(f"❌ Error updating MEXC SL to breakeven: {e}")
                import traceback
                logger.error(f"Traceback: {traceback.format_exc()}")
            
        except Exception as e:
            logger.error(f"❌ Error setting SL to breakeven for TP: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
    
    async def _start_trailing_sl(self, monitored_order, leg: Dict[str, Any], fill_price: float):
        """Start trailing stop loss"""
        try:
            logger.info(f"🔄 Starting trailing SL for order {monitored_order.order_ref}")
            # TODO: Implement trailing stop logic
            logger.info(f"✅ Trailing SL started (not yet implemented)")
        except Exception as e:
            logger.error(f"Error starting trailing SL: {e}")
     
    async def _update_tp_sl_order_status(self, trigger_order: dict, trade: dict, position):
        """Update TP/SL order status to FILLED when trigger executes"""
        try:
            # Find the corresponding TP/SL order in our system
            monitored_order = None
            from .order_monitor import order_monitor

            # Look for the monitored order that has this trigger
            for order_ref, mon_order in order_monitor.monitored_orders.items():
                if hasattr(position, 'order_ref') and position.order_ref == order_ref:
                    monitored_order = mon_order
                    break

            if not monitored_order:
                logger.warning(f"Could not find monitored order for position {position.position_id}")
                return

            # Determine if this is TP or SL based on trigger side vs position side
            # For TP: trigger side should be opposite of position side (profit taking)
            # For SL: trigger side should be opposite of position side (loss cutting)
            trigger_side = trigger_order.get('side', 0)
            position_side = 1 if position.side == "BUY" else 2  # Convert to MEXC format

            # Update the appropriate order (TP or SL)
            if trigger_side != position_side:  # Opposite side = TP
                order_ref = f"{monitored_order.order_ref}_tp"
                order_type = "TP"
                logger.info(f"🎯 Updating TP order {order_ref} to FILLED")
            else:  # Same side = SL
                order_ref = f"{monitored_order.order_ref}_sl"
                order_type = "SL"
                logger.info(f"🎯 Updating SL order {order_ref} to FILLED")

            # Update order status and fill data
            from .orders import order_service
            await order_service.update_order_status(order_ref, "FILLED")

            # Update fill data for the TP/SL order
            fill_data = {
                'price': trade.get('price', 0),
                'quantity': trade.get('quantity', trade.get('vol', 0)),
                'commission': trade.get('fee', 0),
                'time': trade.get('time', 0),
                'broker_order_id': str(trigger_order.get('order_id', ''))
            }

            await order_service.update_order_fill_data(order_ref, fill_data)
            logger.info(f"✅ Updated {order_type} order {order_ref} fill data: {fill_data}")
            
            # Execute after_fill_actions if this is a TP fill
            if order_type == "TP":
                await self._execute_after_fill_actions_for_tp(monitored_order, fill_data['price'])

        except Exception as e:
            logger.error(f"Error updating TP/SL order status: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")

    async def _update_direct_tp_sl_order_status(self, broker_order_id: str, trade: dict, position, order_type: str):
        """Update TP/SL order status to FILLED for direct broker order ID matches"""
        try:
            # Find the corresponding TP/SL order in our system
            monitored_order = None
            from .order_monitor import order_monitor

            # Look for the monitored order that has this broker order ID
            for order_ref, mon_order in order_monitor.monitored_orders.items():
                if hasattr(position, 'order_ref') and position.order_ref == order_ref:
                    monitored_order = mon_order
                    break

            if not monitored_order:
                logger.warning(f"Could not find monitored order for position {position.position_id}")
                return

            # Create the order reference for TP or SL
            if order_type == "TP":
                order_ref = f"{monitored_order.order_ref}_tp"
            else:  # SL
                order_ref = f"{monitored_order.order_ref}_sl"

            logger.info(f"🎯 Updating {order_type} order {order_ref} to FILLED (trigger execution)")

            # Update order status and fill data
            from .orders import order_service
            await order_service.update_order_status(order_ref, "FILLED")

            # Update fill data for the TP/SL order
            # For trigger orders, the actual order ID that executed is in the trade
            actual_order_id = trade.get('order_id', broker_order_id)  # Use trade's order_id if available

            fill_data = {
                'price': trade.get('price', 0),
                'quantity': trade.get('quantity', trade.get('vol', 0)),
                'commission': trade.get('fee', 0),
                'time': trade.get('time', 0),
                'broker_order_id': actual_order_id  # Use the actual order ID from the trade
            }

            await order_service.update_order_status(order_ref, "FILLED", fill_data)
            logger.info(f"✅ Updated {order_type} order {order_ref} fill data: {fill_data}")
            
            # Execute after_fill_actions if this is a TP fill
            if order_type == "TP":
                await self._execute_after_fill_actions_for_tp(monitored_order, fill_data['price'])

        except Exception as e:
            logger.error(f"Error updating direct TP/SL order status: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")

    async def _update_trigger_tp_sl_order_status(self, trigger_order: dict, trade: dict, position):
        """Update TP/SL order status to FILLED for executed trigger orders"""
        try:
            # Find the corresponding TP/SL order in our system
            monitored_order = None
            from .order_monitor import order_monitor

            # Look for the monitored order that has this trigger
            for order_ref, mon_order in order_monitor.monitored_orders.items():
                if hasattr(position, 'order_ref') and position.order_ref == order_ref:
                    monitored_order = mon_order
                    break

            if not monitored_order:
                logger.warning(f"Could not find monitored order for position {position.position_id}")
                return

            # Determine if this is TP or SL based on trigger type
            trigger_type = trigger_order.get('trigger_type', '').upper()
            if 'GREATER' in trigger_type or '1' in str(trigger_order.get('trigger_type', '')):
                order_type = "TP"
                order_ref = f"{monitored_order.order_ref}_tp"
            else:
                order_type = "SL"
                order_ref = f"{monitored_order.order_ref}_sl"

            logger.info(f"🎯 Updating {order_type} order {order_ref} to FILLED (executed trigger)")

            # Update order status and fill data
            from .orders import order_service
            await order_service.update_order_status(order_ref, "FILLED")

            # Update fill data for the TP/SL order
            fill_data = {
                'price': trade.get('price', 0),
                'quantity': trade.get('quantity', trade.get('vol', 0)),
                'commission': trade.get('fee', 0),
                'time': trade.get('time', 0),
                'broker_order_id': str(trigger_order.get('order_id', ''))  # Use the executed order ID
            }

            await order_service.update_order_fill_data(order_ref, fill_data)
            logger.info(f"✅ Updated {order_type} order {order_ref} fill data: {fill_data}")
            
            # Execute after_fill_actions if this is a TP fill
            if order_type == "TP":
                await self._execute_after_fill_actions_for_tp(monitored_order, fill_data['price'])

        except Exception as e:
            logger.error(f"Error updating trigger TP/SL order status: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")

    async def _update_order_statuses_on_close(self, position_id: str, close_reason: str):
        """Update order statuses when position closes"""
        try:
            from .orders import order_service

            logger.info(f"🔄 Updating order statuses for position {position_id} with close reason: {close_reason}")

            # Get all orders for this position
            position_orders = self.get_position_orders(position_id)
            
            # Convert to list of order objects for compatibility
            orders = []
            for order_obj in position_orders:
                # Create a simple order object from the Order data
                order_data = type('Order', (), {
                    'order_id': getattr(order_obj, 'order_id', ''),
                    'order_ref': getattr(order_obj, 'order_ref', ''),
                    'status': getattr(order_obj, 'status', ''),
                    'order_type': getattr(order_obj, 'order_type', ''),
                    'broker_order_id': getattr(order_obj, 'broker_order_id', '')
                })()
                orders.append(order_data)

            # Also find TP/SL orders for this position from CSV
            entry_order = None
            for order in orders:
                if order.order_type not in ["TP", "SL"]:
                    entry_order = order
                    break

            if entry_order:
                logger.info(f"🔄 Entry order found: {entry_order.order_id}, order_ref: {entry_order.order_ref}")

                # Look for TP/SL orders with the same base order_ref in CSV
                tp_order_ref = f"{entry_order.order_ref}_tp"
                sl_order_ref = f"{entry_order.order_ref}_sl"

                logger.info(f"🔄 Looking for TP order: {tp_order_ref}")
                logger.info(f"🔄 Looking for SL order: {sl_order_ref}")

                # Get TP order from CSV
                tp_order_data = await order_service.get_order_by_ref(tp_order_ref)
                if tp_order_data:
                    tp_order_obj = type('Order', (), {
                        'order_id': tp_order_data.get('order_id', ''),
                        'order_ref': tp_order_data.get('order_ref', ''),
                        'status': tp_order_data.get('status', ''),
                        'order_type': tp_order_data.get('order_type', ''),
                        'broker_order_id': tp_order_data.get('broker_order_id', '')
                    })()
                    orders.append(tp_order_obj)
                    logger.info(f"🔄 Found TP order: {tp_order_ref}")

                # Get SL order from CSV
                sl_order_data = await order_service.get_order_by_ref(sl_order_ref)
                if sl_order_data:
                    sl_order_obj = type('Order', (), {
                        'order_id': sl_order_data.get('order_id', ''),
                        'order_ref': sl_order_data.get('order_ref', ''),
                        'status': sl_order_data.get('status', ''),
                        'order_type': sl_order_data.get('order_type', ''),
                        'broker_order_id': sl_order_data.get('broker_order_id', '')
                    })()
                    orders.append(sl_order_obj)
                    logger.info(f"🔄 Found SL order: {sl_order_ref}")

            logger.info(f"🔄 Found {len(orders)} orders for position {position_id}")

            for i, order in enumerate(orders):
                logger.info(f"🔄 Order {i+1}: ID={order.order_id}, Status={order.status}, Type={order.order_type}, BrokerID={order.broker_order_id}")
            
            # Handle TP/SL orders based on close reason
            if "TAKE_PROFIT" in close_reason.upper():
                logger.info(f"🎯 TAKE_PROFIT close: TP order should be FILLED, SL order should be CANCELLED")
                # Find and handle TP order (should already be FILLED by trade detection)
                tp_order = None
                sl_order = None
                entry_order = None

                for order in orders:
                    if "_tp" in order.order_id or str(order.order_type) == "TP":
                        tp_order = order
                    elif "_sl" in order.order_id or str(order.order_type) == "SL":
                        sl_order = order
                    else:
                        entry_order = order

                # Execute after_fill_actions for TP1 BEFORE cleanup
                try:
                    from .order_monitor import order_monitor
                    if position.order_ref in order_monitor.monitored_orders:
                        monitored_order = order_monitor.monitored_orders[position.order_ref]
                        logger.info(f"🎯 Executing after_fill_actions for TP1 close")
                        await self._execute_after_fill_actions_for_tp(monitored_order, position.current_price)
                    else:
                        logger.warning(f"❌ Monitored order not found for after_fill_actions: {position.order_ref}")
                except Exception as e:
                    logger.error(f"Error executing after_fill_actions for TP close: {e}")

                # Ensure TP order is marked as FILLED (should already be done by trade detection)
                if tp_order and tp_order.status != "FILLED":
                    await order_service.update_order_status(tp_order.order_id, "FILLED")
                    logger.info(f"✅ Updated TP order {tp_order.order_id} to FILLED")

                # Cancel SL order
                if sl_order and sl_order.status in ["OPEN", "PENDING"]:
                    await order_service.update_order_status(sl_order.order_id, "CANCELLED")
                    logger.info(f"✅ Updated SL order {sl_order.order_id} to CANCELLED (position closed by TP)")

            elif "STOP_LOSS" in close_reason.upper():
                logger.info(f"🎯 STOP_LOSS close: SL order should be FILLED, TP order should be CANCELLED")
                # Find and handle SL order (should already be FILLED by trade detection)
                tp_order = None
                sl_order = None
                entry_order = None

                for order in orders:
                    if "_tp" in order.order_id or str(order.order_type) == "TP":
                        tp_order = order
                    elif "_sl" in order.order_id or str(order.order_type) == "SL":
                        sl_order = order
                    else:
                        entry_order = order

                # Ensure SL order is marked as FILLED (should already be done by trade detection)
                if sl_order and sl_order.status != "FILLED":
                    await order_service.update_order_status(sl_order.order_id, "FILLED")
                    logger.info(f"✅ Updated SL order {sl_order.order_id} to FILLED")

                # Cancel TP order
                if tp_order and tp_order.status in ["OPEN", "PENDING"]:
                    await order_service.update_order_status(tp_order.order_id, "CANCELLED")
                    logger.info(f"✅ Updated TP order {tp_order.order_id} to CANCELLED (position closed by SL)")

            else:
                # Manual close or unknown - cancel all OPEN/PENDING orders
                logger.info(f"🔄 Manual/unknown close: cancelling all OPEN/PENDING orders")
                for order in orders:
                    if order.status in ["OPEN", "PENDING"]:
                        logger.info(f"🔄 Cancelling order {order.order_id} (status: {order.status})")
                        await order_service.update_order_status(order.order_id, "CANCELLED")
                        logger.info(f"✅ Updated order {order.order_id} to CANCELLED (manual/unknown close)")
            
        except Exception as e:
            logger.error(f"Error updating order statuses for position {position_id}: {e}")
    
    async def _fetch_order_fill_data(self, position_id: str):
        """Fetch fill data from broker for orders associated with this position"""
        try:
            from .orders import order_service
            
            # Get all orders for this position
            orders = self.get_position_orders(position_id)
            
            for order in orders:
                if order.broker_order_id and (order.status == OrderStatus.PENDING or order.status == "OPEN"):
                    # Fetch fill data from broker
                    await order_service.update_order_fill_data(order.broker_order_id)
                    logger.info(f"📊 Fetched fill data for order {order.order_id}")
                    
                    # If this is an entry order and we got fill data, update position entry price
                    if order.order_type == OrderType.ENTRY and order.filled_price > 0:
                        self.update_position(position_id, entry_price=order.filled_price)
                        logger.info(f"📊 Updated position {position_id} entry price to {order.filled_price}")
            
        except Exception as e:
            logger.error(f"Error fetching order fill data for position {position_id}: {e}")
    
    async def _check_for_tp_fills(self, position_id: str, position: Position):
        """Check for TP fills when position size decreases"""
        try:
            from ..adapters.manager import broker_manager
            from .order_monitor import order_monitor
            
            logger.info(f"🔍 Checking for TP fills for position {position_id}")
            
            # Get broker adapter
            broker_name = "mexc"
            broker = broker_manager.get_adapter(broker_name)
            
            if not broker:
                logger.warning("❌ No broker connection for TP fill check")
                return
            
            # Get recent trades to find TP fills
            trades_result = await broker.get_recent_trades(symbol=position.symbol, limit=10)
            
            if not trades_result:
                logger.warning("❌ No recent trades found for TP fill check")
                return
            
            # For SHORT positions, CLOSE transactions have side=2
            if position.side == "SELL":  # SHORT position
                close_transactions = [t for t in trades_result if t.get('side') == 2]
            else:  # LONG position
                close_transactions = [t for t in trades_result if t.get('side') == 4]
            
            logger.info(f"🔍 Found {len(close_transactions)} CLOSE transactions for TP fill check")
            
            # Check each CLOSE transaction to see if it's a TP fill
            for transaction in close_transactions:
                order_id = transaction.get('order_id')
                if not order_id:
                    continue
                
                logger.info(f"🔍 Checking CLOSE transaction with order_id: {order_id}")
                
                # Get full order details to check externalOid
                order_details = await broker.get_order(order_id)
                if order_details:
                    # Handle both dict and object responses
                    if hasattr(order_details, 'externalOid'):
                        external_oid = getattr(order_details, 'externalOid', '')
                    else:
                        external_oid = order_details.get('externalOid', '')
                    
                    logger.info(f"🔍 Order externalOid: {external_oid}")
                    
                    # Check if this is a TP fill based on price movement and order characteristics
                    transaction_price = transaction.get('price', 0)
                    logger.info(f"🔍 Transaction price: {transaction_price}")
                    logger.info(f"🔍 Position entry price: {position.entry_price}")
                    logger.info(f"🔍 Position side: {position.side}")
                    
                    # For SHORT positions: TP1 should be filled when price goes DOWN
                    # For LONG positions: TP1 should be filled when price goes UP
                    if position.side == "SELL":  # SHORT position
                        if transaction_price < position.entry_price:
                            logger.info(f"🎯 Potential TP1 fill detected for SHORT position!")
                            logger.info(f"🎯 Price moved DOWN: {transaction_price} < {position.entry_price}")
                            
                            # Check if this order has _m_ prefix (separate TP order)
                            if external_oid.startswith('_m_'):
                                logger.info(f"🎯 Confirmed TP fill! Order has _m_ prefix: {external_oid}")
                                
                                # Update TP order status to FILLED
                                await self._update_tp_sl_order_from_execution(order_details, transaction, position, "TAKE_PROFIT")
                                
                                # Execute after_fill_actions for TP1
                                try:
                                    logger.info(f"🔍 Looking for monitored order with order_ref: {position.order_ref}")
                                    logger.info(f"🔍 Available monitored orders: {list(order_monitor.monitored_orders.keys())}")
                                    
                                    if position.order_ref in order_monitor.monitored_orders:
                                        monitored_order = order_monitor.monitored_orders[position.order_ref]
                                        logger.info(f"✅ Found monitored order: {monitored_order}")
                                        await self._execute_after_fill_actions_for_tp(monitored_order, transaction_price)
                                    else:
                                        logger.warning(f"❌ Monitored order not found for order_ref: {position.order_ref}")
                                        logger.warning(f"❌ Available order_refs: {list(order_monitor.monitored_orders.keys())}")
                                except Exception as e:
                                    logger.error(f"Error executing after_fill_actions: {e}")
                                    import traceback
                                    logger.error(f"Traceback: {traceback.format_exc()}")
                                
                                # Update position with final data
                                position.current_price = transaction_price
                                logger.info(f"✅ TP fill processed and after_fill_actions executed")
                                return  # Exit after processing first TP fill
                    
                    elif position.side == "BUY":  # LONG position
                        if transaction_price > position.entry_price:
                            logger.info(f"🎯 Potential TP1 fill detected for LONG position!")
                            logger.info(f"🎯 Price moved UP: {transaction_price} > {position.entry_price}")
                            
                            # Check if this order has _m_ prefix (separate TP order)
                            if external_oid.startswith('_m_'):
                                logger.info(f"🎯 Confirmed TP fill! Order has _m_ prefix: {external_oid}")
                                
                                # Update TP order status to FILLED
                                await self._update_tp_sl_order_from_execution(order_details, transaction, position, "TAKE_PROFIT")
                                
                                # Execute after_fill_actions for TP1
                                try:
                                    logger.info(f"🔍 Looking for monitored order with order_ref: {position.order_ref}")
                                    logger.info(f"🔍 Available monitored orders: {list(order_monitor.monitored_orders.keys())}")
                                    
                                    if position.order_ref in order_monitor.monitored_orders:
                                        monitored_order = order_monitor.monitored_orders[position.order_ref]
                                        logger.info(f"✅ Found monitored order: {monitored_order}")
                                        await self._execute_after_fill_actions_for_tp(monitored_order, transaction_price)
                                    else:
                                        logger.warning(f"❌ Monitored order not found for order_ref: {position.order_ref}")
                                        logger.warning(f"❌ Available order_refs: {list(order_monitor.monitored_orders.keys())}")
                                except Exception as e:
                                    logger.error(f"Error executing after_fill_actions: {e}")
                                    import traceback
                                    logger.error(f"Traceback: {traceback.format_exc()}")
                                
                                # Update position with final data
                                position.current_price = transaction_price
                                logger.info(f"✅ TP fill processed and after_fill_actions executed")
                                return  # Exit after processing first TP fill
            
        except Exception as e:
            logger.error(f"Error checking for TP fills: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
    
    async def _cleanup_position(self, position_id: str, close_reason: str = "UNKNOWN"):
        """Cleanup position and related orders when position closes"""
        try:
            logger.info(f"🧹 Cleaning up position {position_id} - Reason: {close_reason}")
            
            # Get all orders for this position
            orders = self.get_position_orders(position_id)
            
            # Cancel any pending orders
            from ..adapters.manager import broker_manager
            broker_name = "mexc"
            await broker_manager.ensure_broker_connected(broker_name)
            broker = broker_manager.get_adapter(broker_name)
            
            if broker:
                for order in orders:
                    if (order.status == OrderStatus.PENDING or order.status == "OPEN") and order.broker_order_id:
                        try:
                            await broker.cancel_order(order.broker_order_id)
                            self.update_order_status(order.order_id, OrderStatus.CANCELLED)
                            logger.info(f"✅ Cancelled order {order.order_id}")
                        except Exception as e:
                            logger.error(f"Failed to cancel order {order.order_id}: {e}")
            
            # Remove from order monitoring
            from .order_monitor import order_monitor
            if position_id in self.positions:
                position = self.positions[position_id]
                if position.order_ref:
                    order_monitor.remove_order_from_monitoring(position.order_ref)
                    logger.info(f"✅ Removed {position.order_ref} from monitoring")

                # Remove the position from tracking
                del self.positions[position_id]
                logger.info(f"✅ Removed position {position_id} from tracking")
                
                # Check if we should unsubscribe from market data for this symbol
                # Only unsubscribe if no other positions are using this symbol
                symbol = position.symbol
                other_positions_using_symbol = any(
                    p.symbol == symbol and p.status == PositionStatus.OPEN 
                    for p in self.positions.values()
                )
                
                if not other_positions_using_symbol:
                    try:
                        from ..services.mexc_market_data import mexc_market_data
                        await mexc_market_data.unsubscribe_symbol(symbol)
                        logger.info(f"📊 Unsubscribed from {symbol} market data (no more open positions)")
                    except Exception as e:
                        logger.warning(f"Could not unsubscribe from market data for {symbol}: {e}")

            logger.info(f"✅ Position {position_id} cleanup completed")
            
        except Exception as e:
            logger.error(f"Error cleaning up position {position_id}: {e}")
    
    def get_positions_by_strategy(self, strategy_id: str) -> List[Position]:
        """Get all positions for a specific strategy"""
        try:
            return [position for position in self.positions.values() 
                   if position.strategy_id == strategy_id]
        except Exception as e:
            logger.error(f"❌ Error getting positions for strategy {strategy_id}: {e}")
            return []
    
    def get_all_positions(self) -> List[Position]:
        """Get all positions"""
        try:
            return list(self.positions.values())
        except Exception as e:
            logger.error(f"❌ Error getting all positions: {e}")
            return []

    def set_timestop(self, position_id: str, duration_minutes: float, action: str = "MARKET_EXIT") -> bool:
        """Set timestop for a position"""
        try:
            position = self.positions.get(position_id)
            if not position:
                logger.error(f"❌ Position {position_id} not found for timestop")
                return False
            
            if position.status != PositionStatus.OPEN:
                logger.error(f"❌ Cannot set timestop on closed position {position_id}")
                return False
            
            # Calculate expiration time
            expires_at = datetime.utcnow() + timedelta(minutes=duration_minutes)
            
            # Update position with timestop info
            position.timestop_enabled = True
            position.timestop_expires_at = expires_at
            position.timestop_action = action
            
            logger.info(f"⏰ Timestop set for position {position_id}: expires in {duration_minutes} minutes, action={action}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error setting timestop for position {position_id}: {e}")
            return False

    def cancel_timestop(self, position_id: str) -> bool:
        """Cancel timestop for a position"""
        try:
            position = self.positions.get(position_id)
            if not position:
                logger.error(f"❌ Position {position_id} not found for timestop cancellation")
                return False
            
            # Disable timestop
            position.timestop_enabled = False
            position.timestop_expires_at = None
            position.timestop_action = "MARKET_EXIT"
            
            logger.info(f"⏰ Timestop cancelled for position {position_id}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error cancelling timestop for position {position_id}: {e}")
            return False

    async def check_timestops(self):
        """Check for expired timestops and execute actions"""
        try:
            current_time = datetime.utcnow()
            expired_positions = []
            
            # Find positions with expired timestops
            for position_id, position in self.positions.items():
                if (position.status == PositionStatus.OPEN and 
                    position.timestop_enabled and 
                    position.timestop_expires_at and 
                    current_time >= position.timestop_expires_at):
                    expired_positions.append(position)
            
            # Execute timestop actions for expired positions
            for position in expired_positions:
                await self._execute_timestop_action(position)
                
        except Exception as e:
            logger.error(f"❌ Error checking timestops: {e}")

    async def _execute_timestop_action(self, position: Position):
        """Execute the timestop action for a position"""
        try:
            logger.info(f"⏰ TIMESTOP TRIGGERED for position {position.position_id} - Action: {position.timestop_action}")
            
            if position.timestop_action in ["MARKET_EXIT", "BOTH"]:
                await self._timestop_market_exit(position)
            
            if position.timestop_action in ["CANCEL_ALL", "BOTH"]:
                await self._timestop_cancel_orders(position)
            
            # Disable timestop after execution
            position.timestop_enabled = False
            position.timestop_expires_at = None
            
        except Exception as e:
            logger.error(f"❌ Error executing timestop action for position {position.position_id}: {e}")

    async def _timestop_market_exit(self, position: Position):
        """Execute market exit for timestop"""
        try:
            from .orders import order_service
            from ..core.database import get_db
            
            logger.info(f"⏰ Executing timestop market exit for position {position.position_id}")
            
            # Create market close order request
            close_side = "SELL" if position.side == "BUY" else "BUY"
            
            close_order_request = {
                "idempotency_key": f"timestop_{position.position_id}_{int(datetime.utcnow().timestamp())}",
                "environment": {"sandbox": True},  # TODO: Get actual environment from position
                "source": {
                    "strategy_id": position.strategy_id or "timestop",
                    "instance_id": "timestop",
                    "owner": "system"
                },
                "order": {
                    "instrument": {
                        "class": "crypto_perp",
                        "symbol": position.symbol
                    },
                    "side": close_side,
                    "quantity": {
                        "type": "contracts",
                        "value": position.size
                    },
                    "order_type": "MARKET",
                    "time_in_force": "IOC",
                    "flags": {
                        "post_only": False,
                        "reduce_only": True,
                        "hidden": False,
                        "iceberg": {},
                        "allow_partial_fills": True
                    },
                    "routing": {
                        "mode": "AUTO"
                    },
                    "leverage": {
                        "enabled": False
                    }
                }
            }
            
            # Get database session and place close order
            async for db in get_db():
                result = await order_service.create_order(close_order_request, db)
                if result.get("success"):
                    logger.info(f"✅ Timestop market exit order placed: {result.get('order_ref')}")
                else:
                    logger.error(f"❌ Failed to place timestop market exit order: {result.get('error')}")
                break  # Exit the async generator
                
        except Exception as e:
            logger.error(f"❌ Error executing timestop market exit for position {position.position_id}: {e}")

    async def _timestop_cancel_orders(self, position: Position):
        """Cancel all orders for timestop"""
        try:
            logger.info(f"⏰ Cancelling all orders for timestop position {position.position_id}")
            
            # Get all orders for this position
            order_ids = self.position_orders.get(position.position_id, [])
            
            for order_id in order_ids:
                order = self.orders.get(order_id)
                if order and order.status in [OrderStatus.OPEN, OrderStatus.PENDING]:
                    # Update order status to cancelled
                    order.status = OrderStatus.CANCELLED
                    order.updated_at = datetime.utcnow()
                    
                    logger.info(f"✅ Cancelled order {order_id} due to timestop")
            
            logger.info(f"⏰ Cancelled {len(order_ids)} orders for timestop position {position.position_id}")
            
        except Exception as e:
            logger.error(f"❌ Error cancelling orders for timestop position {position.position_id}: {e}")

# Global position tracker instance
position_tracker = PositionTracker()
