"""
Comprehensive Data Logging System
Tracks all trading data, balances, PnL, and performance metrics
"""
import csv
import json
import logging
import os
import redis.asyncio as redis
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from pathlib import Path
import asyncio

logger = logging.getLogger(__name__)

@dataclass
class OrderLogEntry:
    """Order log entry for CSV"""
    timestamp: str
    order_id: str
    strategy_id: str
    account_id: str
    symbol: str
    side: str
    order_type: str
    quantity: float
    price: float
    stop_price: Optional[float]
    time_in_force: str
    status: str
    broker: str
    broker_order_id: str
    position_id: str
    leverage: float
    margin_used: float
    commission: float
    fill_price: Optional[float]
    fill_quantity: Optional[float]
    fill_time: Optional[str]

@dataclass
class PositionLogEntry:
    """Position log entry for CSV"""
    timestamp: str
    position_id: str
    strategy_id: str
    account_id: str
    symbol: str
    side: str
    size: float
    entry_price: float
    exit_price: float
    realized_pnl: float
    total_fees: float
    volume: float
    leverage: float
    status: str  # OPEN, CLOSED, PARTIAL
    open_time: str
    close_time: Optional[str]
    duration_seconds: Optional[int]
    max_favorable: float  # Best PnL during position
    max_adverse: float    # Worst PnL during position
    exit_reason: Optional[str]

@dataclass
class AccountBalanceEntry:
    """Account balance log entry"""
    timestamp: str
    account_id: str
    strategy_id: str
    total_balance: float
    available_balance: float
    margin_used: float
    unrealized_pnl: float
    realized_pnl: float
    total_pnl: float
    daily_pnl: float
    weekly_pnl: float
    monthly_pnl: float
    max_drawdown: float
    max_drawdown_percent: float
    win_rate: float
    total_trades: int
    winning_trades: int
    losing_trades: int
    avg_win: float
    avg_loss: float
    profit_factor: float
    sharpe_ratio: float
    total_volume: float
    active_positions: int

@dataclass
class TotalBalanceEntry:
    """Total account balance aggregation"""
    timestamp: str
    total_balance: float
    total_available: float
    total_margin_used: float
    total_unrealized_pnl: float
    total_realized_pnl: float
    total_daily_pnl: float
    total_weekly_pnl: float
    total_monthly_pnl: float
    total_max_drawdown: float
    total_max_drawdown_percent: float
    total_trades: int
    total_volume: float
    active_positions: int
    active_strategies: int
    active_accounts: int

@dataclass
class StrategyPerformanceEntry:
    """Strategy performance metrics"""
    timestamp: str
    strategy_id: str
    total_pnl: float
    daily_pnl: float
    weekly_pnl: float
    monthly_pnl: float
    max_drawdown: float
    max_drawdown_percent: float
    win_rate: float
    total_trades: int
    winning_trades: int
    losing_trades: int
    avg_win: float
    avg_loss: float
    profit_factor: float
    sharpe_ratio: float
    total_volume: float
    active_positions: int
    avg_position_duration: float
    best_trade: float
    worst_trade: float
    consecutive_wins: int
    consecutive_losses: int



class DataLogger:
    """Comprehensive data logging system"""
    
    def __init__(self):
        self.base_dir = Path("data/logs")
        self.base_dir.mkdir(parents=True, exist_ok=True)
        
        # Create subdirectories
        (self.base_dir / "orders").mkdir(exist_ok=True)
        (self.base_dir / "positions").mkdir(exist_ok=True)
        (self.base_dir / "balances").mkdir(exist_ok=True)
        (self.base_dir / "strategies").mkdir(exist_ok=True)
        (self.base_dir / "performance").mkdir(exist_ok=True)
        
        # Redis connection for real-time data
        self.redis_client: Optional[redis.Redis] = None
        
        # CSV file paths
        self.main_orders_csv = self.base_dir / "orders" / "main_orders.csv"
        self.main_positions_csv = self.base_dir / "positions" / "main_positions.csv"
        self.total_balance_csv = self.base_dir / "balances" / "total_balance.csv"
        
        # Initialize CSV headers
        self._initialize_csv_headers()
        
        # Performance tracking
        self.performance_cache = {}
        self.last_balance_update = {}
        
    async def initialize_redis(self):
        """Initialize Redis connection"""
        try:
            self.redis_client = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)
            await self.redis_client.ping()
            logger.info("✅ Redis connection established for data logging")
        except Exception as e:
            logger.error(f"❌ Failed to connect to Redis: {e}")
            self.redis_client = None
    
    def _initialize_csv_headers(self):
        """Initialize CSV files with headers"""
        # Main orders CSV
        if not self.main_orders_csv.exists():
            with open(self.main_orders_csv, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow([
                    'timestamp', 'order_id', 'strategy_id', 'account_id', 'symbol', 'side',
                    'order_type', 'quantity', 'price', 'stop_price', 'time_in_force', 'status',
                    'broker', 'broker_order_id', 'position_id', 'leverage', 'margin_used',
                    'commission', 'fill_price', 'fill_quantity', 'fill_time'
                ])
        
        # Main positions CSV
        if not self.main_positions_csv.exists():
            with open(self.main_positions_csv, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow([
                    'timestamp', 'position_id', 'strategy_id', 'account_id', 'symbol', 'side',
                    'size', 'entry_price', 'exit_price',
                    'realized_pnl', 'total_fees', 'volume', 'leverage', 'status', 'open_time', 'close_time',
                    'duration_seconds', 'max_favorable', 'max_adverse', 'exit_reason'
                ])
        
        # Total balance CSV
        if not self.total_balance_csv.exists():
            with open(self.total_balance_csv, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow([
                    'timestamp', 'total_balance', 'total_available', 'total_margin_used',
                    'total_unrealized_pnl', 'total_realized_pnl', 'total_daily_pnl',
                    'total_weekly_pnl', 'total_monthly_pnl', 'total_max_drawdown',
                    'total_max_drawdown_percent', 'total_trades', 'total_volume',
                    'active_positions', 'active_strategies', 'active_accounts'
                ])
        

    
    async def log_order(self, order_data: Dict[str, Any]):
        """Log order to main CSV and strategy-specific CSV"""
        try:
            # Create order log entry
            entry = OrderLogEntry(
                timestamp=datetime.utcnow().isoformat(),
                order_id=order_data.get('order_id', ''),
                strategy_id=order_data.get('strategy_id', ''),
                account_id=order_data.get('account_id', ''),
                symbol=order_data.get('symbol', ''),
                side=order_data.get('side', ''),
                order_type=order_data.get('order_type', ''),
                quantity=float(order_data.get('quantity', 0)) if order_data.get('quantity') is not None else 0.0,
                price=float(order_data.get('price', 0)) if order_data.get('price') is not None else 0.0,
                stop_price=float(order_data.get('stop_price', 0)) if order_data.get('stop_price') is not None else None,
                time_in_force=order_data.get('time_in_force', ''),
                status=order_data.get('status', ''),
                broker=order_data.get('broker', ''),
                broker_order_id=order_data.get('broker_order_id', ''),
                position_id=order_data.get('position_id', ''),
                leverage=float(order_data.get('leverage', 1)) if order_data.get('leverage') is not None else 1.0,
                margin_used=float(order_data.get('margin_used', 0)) if order_data.get('margin_used') is not None else 0.0,
                commission=float(order_data.get('commission', 0)) if order_data.get('commission') is not None else 0.0,
                fill_price=float(order_data.get('fill_price', 0)) if order_data.get('fill_price') is not None else None,
                fill_quantity=float(order_data.get('fill_quantity', 0)) if order_data.get('fill_quantity') is not None else None,
                fill_time=order_data.get('fill_time', '')
            )
            
            # Write to main orders CSV
            # Create dict without position-specific fields
            order_dict = asdict(entry)
            if 'pnl' in order_dict:
                del order_dict['pnl']
            if 'exit_reason' in order_dict:
                del order_dict['exit_reason']
            await self._write_to_csv(self.main_orders_csv, order_dict)
            
            # Write to strategy-specific CSV
            strategy_id = entry.strategy_id
            if strategy_id:
                strategy_orders_csv = self.base_dir / "orders" / f"strategy_{strategy_id}_orders.csv"
                strategy_dict = asdict(entry)
                if 'pnl' in strategy_dict:
                    del strategy_dict['pnl']
                if 'exit_reason' in strategy_dict:
                    del strategy_dict['exit_reason']
                await self._write_to_csv(strategy_orders_csv, strategy_dict)
            
            # Update Redis for real-time access
            if self.redis_client:
                await self._update_redis_order(entry)
            
            logger.info(f"📊 Logged order: {entry.order_id} for strategy {entry.strategy_id}")
            
        except Exception as e:
            logger.error(f"❌ Error logging order: {e}")
    
    async def update_order_fill(self, fill_data: Dict[str, Any]):
        """Update existing order log with fill information"""
        try:
            broker_order_id = fill_data.get('broker_order_id')
            if not broker_order_id:
                logger.error("❌ No broker_order_id provided for fill update")
                return
            
            # Read all orders from CSV to find the matching order
            orders = []
            updated = False
            
            if self.main_orders_csv.exists():
                with open(self.main_orders_csv, 'r', newline='') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        if row.get('broker_order_id') == broker_order_id:
                            # Update fill information
                            row['fill_price'] = str(fill_data.get('fill_price', '')) if fill_data.get('fill_price') is not None else ''
                            row['fill_quantity'] = str(fill_data.get('fill_quantity', '')) if fill_data.get('fill_quantity') is not None else ''
                            row['fill_time'] = fill_data.get('fill_time', '').isoformat() if fill_data.get('fill_time') else ''
                            row['commission'] = str(fill_data.get('commission', '')) if fill_data.get('commission') is not None else ''
                            row['status'] = 'FILLED'  # Update status to filled
                            updated = True
                            logger.info(f"✅ Updated fill data for order {broker_order_id}")
                        orders.append(row)
            
            # Write back to CSV if updated
            if updated and orders:
                with open(self.main_orders_csv, 'w', newline='') as f:
                    if orders:
                        writer = csv.DictWriter(f, fieldnames=orders[0].keys())
                        writer.writeheader()
                        writer.writerows(orders)
            
            # Also update strategy-specific CSV if it exists
            for order in orders:
                if order.get('broker_order_id') == broker_order_id:
                    strategy_id = order.get('strategy_id')
                    if strategy_id:
                        strategy_orders_csv = self.base_dir / "orders" / f"strategy_{strategy_id}_orders.csv"
                        if strategy_orders_csv.exists():
                            # Update strategy-specific CSV
                            strategy_orders = []
                            with open(strategy_orders_csv, 'r', newline='') as f:
                                reader = csv.DictReader(f)
                                for row in reader:
                                    if row.get('broker_order_id') == broker_order_id:
                                        row['fill_price'] = str(fill_data.get('fill_price', '')) if fill_data.get('fill_price') is not None else ''
                                        row['fill_quantity'] = str(fill_data.get('fill_quantity', '')) if fill_data.get('fill_quantity') is not None else ''
                                        row['fill_time'] = fill_data.get('fill_time', '').isoformat() if fill_data.get('fill_time') else ''
                                        row['commission'] = str(fill_data.get('commission', '')) if fill_data.get('commission') is not None else ''
                                        row['pnl'] = str(fill_data.get('pnl', '')) if fill_data.get('pnl') is not None else ''
                                        row['status'] = 'FILLED'
                                    strategy_orders.append(row)
                            
                            if strategy_orders:
                                with open(strategy_orders_csv, 'w', newline='') as f:
                                    writer = csv.DictWriter(f, fieldnames=strategy_orders[0].keys())
                                    writer.writeheader()
                                    writer.writerows(strategy_orders)
                    break
            
        except Exception as e:
            logger.error(f"❌ Error updating order fill: {e}")
    
    async def update_order(self, order_id: str, update_data: Dict[str, Any]):
        """Update existing order log with new data"""
        try:
            # Read all orders from CSV to find the matching order
            orders = []
            updated = False
            
            if self.main_orders_csv.exists():
                with open(self.main_orders_csv, 'r', newline='') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        if row.get('order_id') == order_id:
                            # Update fields with new data (skip pnl and exit_reason if they exist)
                            for key, value in update_data.items():
                                if key in ['pnl', 'exit_reason']:
                                    continue  # Skip position-specific fields
                                if value is not None:
                                    if isinstance(value, datetime):
                                        row[key] = value.isoformat()
                                    else:
                                        row[key] = str(value)
                            updated = True
                            logger.info(f"✅ Updated order {order_id}: {update_data}")
                        orders.append(row)
            
            # Write back to CSV if updated
            if updated and orders:
                with open(self.main_orders_csv, 'w', newline='') as f:
                    if orders:
                        writer = csv.DictWriter(f, fieldnames=orders[0].keys())
                        writer.writeheader()
                        writer.writerows(orders)
            
            # Update strategy-specific CSV if it exists
            if updated:
                strategy_id = None
                for row in orders:
                    if row.get('order_id') == order_id:
                        strategy_id = row.get('strategy_id')
                        break
                
                if strategy_id:
                    strategy_orders_csv = self.base_dir / "orders" / f"strategy_{strategy_id}_orders.csv"
                    if strategy_orders_csv.exists():
                        strategy_orders = []
                        with open(strategy_orders_csv, 'r', newline='') as f:
                            reader = csv.DictReader(f)
                            for row in reader:
                                if row.get('order_id') == order_id:
                                    # Update fields with new data (skip pnl and exit_reason if they exist)
                                    for key, value in update_data.items():
                                        if key in ['pnl', 'exit_reason']:
                                            continue  # Skip position-specific fields
                                        if value is not None:
                                            if isinstance(value, datetime):
                                                row[key] = value.isoformat()
                                            else:
                                                row[key] = str(value)
                                strategy_orders.append(row)
                        
                        if strategy_orders:
                            with open(strategy_orders_csv, 'w', newline='') as f:
                                writer = csv.DictWriter(f, fieldnames=strategy_orders[0].keys())
                                writer.writeheader()
                                writer.writerows(strategy_orders)
            
        except Exception as e:
            logger.error(f"❌ Error updating order {order_id}: {e}")
    
    async def get_order_by_ref(self, order_ref: str) -> Dict[str, Any]:
        """Get order data by order reference from Redis first, then CSV fallback"""
        try:
            logger.info(f"🔍 get_order_by_ref called for: {order_ref}")
            
            # Try Redis first for fast lookup
            if self.redis_client:
                try:
                    redis_data = await self.redis_client.hgetall(f"order:{order_ref}")
                    if redis_data:
                        logger.info(f"✅ Found order in Redis: {order_ref}")
                        return redis_data
                    else:
                        logger.info(f"🔍 Order not found in Redis, trying CSV fallback")
                except Exception as e:
                    logger.warning(f"Redis lookup failed: {e}, trying CSV fallback")
            
            # Fallback to CSV if Redis fails or data not found
            if not self.main_orders_csv.exists():
                logger.warning(f"❌ CSV file does not exist: {self.main_orders_csv}")
                return None
            
            logger.info(f"🔍 Reading CSV file: {self.main_orders_csv}")
            
            with open(self.main_orders_csv, 'r', newline='') as f:
                reader = csv.DictReader(f)
                row_count = 0
                for row in reader:
                    row_count += 1
                    row_order_ref = row.get('order_id', '')  # CSV uses 'order_id' not 'order_ref'
                    
                    if row_order_ref == order_ref:
                        logger.info(f"✅ Found matching order in CSV: {order_ref}")
                        return row
                
                logger.warning(f"❌ No matching order found for {order_ref} in {row_count} rows")
            
            return None
            
        except Exception as e:
            logger.error(f"❌ Error getting order by ref {order_ref}: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            return None
    
    async def log_position(self, position_data: Dict[str, Any]):
        """Log position to main CSV and strategy-specific CSV"""
        try:
            # Create position log entry
            entry = PositionLogEntry(
                timestamp=datetime.utcnow().isoformat(),
                position_id=position_data.get('position_id', ''),
                strategy_id=position_data.get('strategy_id', ''),
                account_id=position_data.get('account_id', ''),
                symbol=position_data.get('symbol', ''),
                side=position_data.get('side', ''),
                size=float(position_data.get('size', 0)) if position_data.get('size') is not None else 0.0,
                entry_price=float(position_data.get('entry_price', 0)) if position_data.get('entry_price') is not None else 0.0,
                exit_price=float(position_data.get('exit_price', 0)) if position_data.get('exit_price') is not None else 0.0,
                realized_pnl=float(position_data.get('realized_pnl', 0)) if position_data.get('realized_pnl') is not None else 0.0,
                total_fees=float(position_data.get('total_fees', 0)) if position_data.get('total_fees') is not None else 0.0,
                volume=float(position_data.get('volume', 0)) if position_data.get('volume') is not None else 0.0,
                leverage=float(position_data.get('leverage', 1)) if position_data.get('leverage') is not None else 1.0,
                status=position_data.get('status', ''),
                open_time=position_data.get('open_time', ''),
                close_time=position_data.get('close_time', ''),
                duration_seconds=position_data.get('duration_seconds'),
                max_favorable=float(position_data.get('max_favorable', 0)) if position_data.get('max_favorable') is not None else 0.0,
                max_adverse=float(position_data.get('max_adverse', 0)) if position_data.get('max_adverse') is not None else 0.0,
                exit_reason=position_data.get('exit_reason', '')
            )
            
            # Write to main positions CSV
            await self._write_to_csv(self.main_positions_csv, asdict(entry))
            
            # Write to strategy-specific CSV
            strategy_id = entry.strategy_id
            if strategy_id:
                strategy_positions_csv = self.base_dir / "positions" / f"strategy_{strategy_id}_positions.csv"
                await self._write_to_csv(strategy_positions_csv, asdict(entry))
            
            # Update Redis for real-time access
            if self.redis_client:
                await self._update_redis_position(entry)
            
            logger.info(f"📊 Logged position: {entry.position_id} for strategy {entry.strategy_id}")
            
        except Exception as e:
            logger.error(f"❌ Error logging position: {e}")
    
    async def log_account_balance(self, account_id: str, balance_data: Dict[str, Any]):
        """Log account balance every 5 minutes"""
        try:
            # Check if we should log (every 5 minutes)
            now = datetime.utcnow()
            last_update = self.last_balance_update.get(account_id)
            
            if last_update and (now - last_update).total_seconds() < 300:  # 5 minutes
                return
            
            # Create balance log entry
            entry = AccountBalanceEntry(
                timestamp=now.isoformat(),
                account_id=account_id,
                strategy_id=balance_data.get('strategy_id', ''),
                total_balance=float(balance_data.get('total_balance', 0)),
                available_balance=float(balance_data.get('available_balance', 0)),
                margin_used=float(balance_data.get('margin_used', 0)),
                unrealized_pnl=float(balance_data.get('unrealized_pnl', 0)),
                realized_pnl=float(balance_data.get('realized_pnl', 0)),
                total_pnl=float(balance_data.get('total_pnl', 0)),
                daily_pnl=float(balance_data.get('daily_pnl', 0)),
                weekly_pnl=float(balance_data.get('weekly_pnl', 0)),
                monthly_pnl=float(balance_data.get('monthly_pnl', 0)),
                max_drawdown=float(balance_data.get('max_drawdown', 0)),
                max_drawdown_percent=float(balance_data.get('max_drawdown_percent', 0)),
                win_rate=float(balance_data.get('win_rate', 0)),
                total_trades=int(balance_data.get('total_trades', 0)),
                winning_trades=int(balance_data.get('winning_trades', 0)),
                losing_trades=int(balance_data.get('losing_trades', 0)),
                avg_win=float(balance_data.get('avg_win', 0)),
                avg_loss=float(balance_data.get('avg_loss', 0)),
                profit_factor=float(balance_data.get('profit_factor', 0)),
                sharpe_ratio=float(balance_data.get('sharpe_ratio', 0)),
                total_volume=float(balance_data.get('total_volume', 0)),
                active_positions=int(balance_data.get('active_positions', 0))
            )
            
            # Write to account-specific CSV
            account_balance_csv = self.base_dir / "balances" / f"account_{account_id}_balance.csv"
            await self._write_to_csv(account_balance_csv, asdict(entry))
            
            # Update Redis
            if self.redis_client:
                await self._update_redis_balance(entry)
            
            self.last_balance_update[account_id] = now
            logger.info(f"📊 Logged balance for account: {account_id}")
            
        except Exception as e:
            logger.error(f"❌ Error logging account balance: {e}")
    
    async def log_total_balance(self, total_data: Dict[str, Any]):
        """Log total balance aggregation every 5-10 seconds"""
        try:
            # Create total balance entry
            entry = TotalBalanceEntry(
                timestamp=datetime.utcnow().isoformat(),
                total_balance=float(total_data.get('total_balance', 0)),
                total_available=float(total_data.get('total_available', 0)),
                total_margin_used=float(total_data.get('total_margin_used', 0)),
                total_unrealized_pnl=float(total_data.get('total_unrealized_pnl', 0)),
                total_realized_pnl=float(total_data.get('total_realized_pnl', 0)),
                total_daily_pnl=float(total_data.get('total_daily_pnl', 0)),
                total_weekly_pnl=float(total_data.get('total_weekly_pnl', 0)),
                total_monthly_pnl=float(total_data.get('total_monthly_pnl', 0)),
                total_max_drawdown=float(total_data.get('total_max_drawdown', 0)),
                total_max_drawdown_percent=float(total_data.get('total_max_drawdown_percent', 0)),
                total_trades=int(total_data.get('total_trades', 0)),
                total_volume=float(total_data.get('total_volume', 0)),
                active_positions=int(total_data.get('active_positions', 0)),
                active_strategies=int(total_data.get('active_strategies', 0)),
                active_accounts=int(total_data.get('active_accounts', 0))
            )
            
            # Write to total balance CSV
            await self._write_to_csv(self.total_balance_csv, asdict(entry))
            
            # Update Redis
            if self.redis_client:
                await self._update_redis_total_balance(entry)
            
            logger.info(f"📊 Logged total balance: ${entry.total_balance:,.2f}")
            
        except Exception as e:
            logger.error(f"❌ Error logging total balance: {e}")
    

    
    async def _write_to_csv(self, file_path: Path, data: Dict[str, Any]):
        """Write data to CSV file"""
        try:
            # Ensure file exists with headers
            if not file_path.exists():
                with open(file_path, 'w', newline='') as f:
                    writer = csv.writer(f)
                    writer.writerow(data.keys())
            
            # Append data
            with open(file_path, 'a', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(data.values())
                
        except Exception as e:
            logger.error(f"❌ Error writing to CSV {file_path}: {e}")
    
    async def _update_redis_order(self, entry: OrderLogEntry):
        """Update Redis with order data"""
        try:
            key = f"order:{entry.order_id}"
            # Use individual hset calls instead of mapping to avoid argument issues
            await self.redis_client.hset(key, 'timestamp', entry.timestamp)
            await self.redis_client.hset(key, 'order_id', entry.order_id)
            await self.redis_client.hset(key, 'strategy_id', entry.strategy_id)
            await self.redis_client.hset(key, 'account_id', entry.account_id)
            await self.redis_client.hset(key, 'symbol', entry.symbol)
            await self.redis_client.hset(key, 'side', entry.side)
            await self.redis_client.hset(key, 'order_type', entry.order_type)
            await self.redis_client.hset(key, 'quantity', str(entry.quantity))
            await self.redis_client.hset(key, 'price', str(entry.price))
            await self.redis_client.hset(key, 'stop_price', str(entry.stop_price) if entry.stop_price is not None else '')
            await self.redis_client.hset(key, 'time_in_force', entry.time_in_force)
            await self.redis_client.hset(key, 'status', entry.status)
            await self.redis_client.hset(key, 'broker', entry.broker)
            await self.redis_client.hset(key, 'broker_order_id', entry.broker_order_id)
            await self.redis_client.hset(key, 'position_id', entry.position_id)
            await self.redis_client.hset(key, 'leverage', str(entry.leverage))
            await self.redis_client.hset(key, 'margin_used', str(entry.margin_used))
            await self.redis_client.hset(key, 'commission', str(entry.commission))
            await self.redis_client.hset(key, 'fill_price', str(entry.fill_price) if entry.fill_price is not None else '')
            await self.redis_client.hset(key, 'fill_quantity', str(entry.fill_quantity) if entry.fill_quantity is not None else '')
            await self.redis_client.hset(key, 'fill_time', entry.fill_time or '')
            await self.redis_client.expire(key, 86400)  # 24 hours
            
            # Add to strategy orders set
            if entry.strategy_id:
                await self.redis_client.sadd(f"strategy:{entry.strategy_id}:orders", entry.order_id)
                
        except Exception as e:
            logger.error(f"❌ Error updating Redis order: {e}")
    
    async def _update_redis_position(self, entry: PositionLogEntry):
        """Update Redis with position data"""
        try:
            key = f"position:{entry.position_id}"
            # Use individual hset calls instead of mapping to avoid argument issues
            await self.redis_client.hset(key, 'timestamp', entry.timestamp)
            await self.redis_client.hset(key, 'position_id', entry.position_id)
            await self.redis_client.hset(key, 'strategy_id', entry.strategy_id)
            await self.redis_client.hset(key, 'account_id', entry.account_id)
            await self.redis_client.hset(key, 'symbol', entry.symbol)
            await self.redis_client.hset(key, 'side', entry.side)
            await self.redis_client.hset(key, 'size', str(entry.size))
            await self.redis_client.hset(key, 'entry_price', str(entry.entry_price))
            await self.redis_client.hset(key, 'exit_price', str(entry.exit_price))
            await self.redis_client.hset(key, 'realized_pnl', str(entry.realized_pnl))
            await self.redis_client.hset(key, 'volume', str(entry.volume))
            await self.redis_client.hset(key, 'leverage', str(entry.leverage))
            await self.redis_client.hset(key, 'status', entry.status)
            await self.redis_client.hset(key, 'open_time', entry.open_time or '')
            await self.redis_client.hset(key, 'close_time', entry.close_time or '')
            await self.redis_client.hset(key, 'duration_seconds', str(entry.duration_seconds) if entry.duration_seconds is not None else '')
            await self.redis_client.hset(key, 'max_favorable', str(entry.max_favorable) if entry.max_favorable is not None else '')
            await self.redis_client.hset(key, 'max_adverse', str(entry.max_adverse) if entry.max_adverse is not None else '')
            await self.redis_client.hset(key, 'exit_reason', entry.exit_reason or '')
            
            # Note: stop_limit_order_id not available in PositionLogEntry
            # If needed, it should be added to the PositionLogEntry class first
            
            # Add to strategy positions set
            if entry.strategy_id:
                await self.redis_client.sadd(f"strategy:{entry.strategy_id}:positions", entry.position_id)
                
        except Exception as e:
            logger.error(f"❌ Error updating Redis position: {e}")
    
    async def _update_redis_balance(self, entry: AccountBalanceEntry):
        """Update Redis with balance data"""
        try:
            key = f"balance:{entry.account_id}"
            # Use individual hset calls instead of mapping to avoid argument issues
            await self.redis_client.hset(key, 'timestamp', entry.timestamp)
            await self.redis_client.hset(key, 'account_id', entry.account_id)
            await self.redis_client.hset(key, 'strategy_id', entry.strategy_id)
            await self.redis_client.hset(key, 'total_balance', str(entry.total_balance))
            await self.redis_client.hset(key, 'available_balance', str(entry.available_balance))
            await self.redis_client.hset(key, 'margin_used', str(entry.margin_used))
            await self.redis_client.hset(key, 'unrealized_pnl', str(entry.unrealized_pnl))
            await self.redis_client.hset(key, 'realized_pnl', str(entry.realized_pnl))
            await self.redis_client.hset(key, 'daily_pnl', str(entry.daily_pnl))
            await self.redis_client.hset(key, 'weekly_pnl', str(entry.weekly_pnl))
            await self.redis_client.hset(key, 'monthly_pnl', str(entry.monthly_pnl))
            await self.redis_client.hset(key, 'max_drawdown', str(entry.max_drawdown))
            await self.redis_client.hset(key, 'max_drawdown_percent', str(entry.max_drawdown_percent))
            await self.redis_client.hset(key, 'total_trades', str(entry.total_trades))
            await self.redis_client.hset(key, 'total_volume', str(entry.total_volume))
            await self.redis_client.hset(key, 'active_positions', str(entry.active_positions))
            await self.redis_client.expire(key, 3600)  # 1 hour
            
        except Exception as e:
            logger.error(f"❌ Error updating Redis balance: {e}")
    
    async def _update_redis_total_balance(self, entry: TotalBalanceEntry):
        """Update Redis with total balance data"""
        try:
            key = "total_balance"
            # Use individual hset calls instead of mapping to avoid argument issues
            await self.redis_client.hset(key, 'timestamp', entry.timestamp)
            await self.redis_client.hset(key, 'total_balance', str(entry.total_balance))
            await self.redis_client.hset(key, 'total_available', str(entry.total_available))
            await self.redis_client.hset(key, 'total_margin_used', str(entry.total_margin_used))
            await self.redis_client.hset(key, 'total_unrealized_pnl', str(entry.total_unrealized_pnl))
            await self.redis_client.hset(key, 'total_realized_pnl', str(entry.total_realized_pnl))
            await self.redis_client.hset(key, 'total_daily_pnl', str(entry.total_daily_pnl))
            await self.redis_client.hset(key, 'total_weekly_pnl', str(entry.total_weekly_pnl))
            await self.redis_client.hset(key, 'total_monthly_pnl', str(entry.total_monthly_pnl))
            await self.redis_client.hset(key, 'total_max_drawdown', str(entry.total_max_drawdown))
            await self.redis_client.hset(key, 'total_max_drawdown_percent', str(entry.total_max_drawdown_percent))
            await self.redis_client.hset(key, 'total_trades', str(entry.total_trades))
            await self.redis_client.hset(key, 'total_volume', str(entry.total_volume))
            await self.redis_client.hset(key, 'active_positions', str(entry.active_positions))
            await self.redis_client.hset(key, 'active_strategies', str(entry.active_strategies))
            await self.redis_client.hset(key, 'active_accounts', str(entry.active_accounts))
            
        except Exception as e:
            logger.error(f"❌ Error updating Redis total balance: {e}")
    

    
    async def get_historical_data(self, data_type: str, strategy_id: Optional[str] = None, 
                                start_time: Optional[datetime] = None, 
                                end_time: Optional[datetime] = None) -> List[Dict[str, Any]]:
        """Get historical data from CSV files"""
        try:
            if data_type == "orders":
                if strategy_id:
                    file_path = self.base_dir / "orders" / f"strategy_{strategy_id}_orders.csv"
                else:
                    file_path = self.main_orders_csv
            elif data_type == "positions":
                if strategy_id:
                    file_path = self.base_dir / "positions" / f"strategy_{strategy_id}_positions.csv"
                else:
                    file_path = self.main_positions_csv
            elif data_type == "total_balance":
                file_path = self.total_balance_csv
            else:
                return []
            
            if not file_path.exists():
                return []
            
            data = []
            with open(file_path, 'r') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    # Filter by time if specified
                    if start_time or end_time:
                        row_time = datetime.fromisoformat(row['timestamp'])
                        if start_time and row_time < start_time:
                            continue
                        if end_time and row_time > end_time:
                            continue
                    
                    data.append(row)
            
            return data
            
        except Exception as e:
            logger.error(f"❌ Error getting historical data: {e}")
            return []
    
    async def get_real_time_data(self, data_type: str, key: str) -> Optional[Dict[str, Any]]:
        """Get real-time data from Redis"""
        try:
            if not self.redis_client:
                return None
            
            if data_type == "order":
                return await self.redis_client.hgetall(f"order:{key}")
            elif data_type == "position":
                return await self.redis_client.hgetall(f"position:{key}")
            elif data_type == "balance":
                return await self.redis_client.hgetall(f"balance:{key}")
            elif data_type == "total_balance":
                return await self.redis_client.hgetall("total_balance")
            
            return None
            
        except Exception as e:
            logger.error(f"❌ Error getting real-time data: {e}")
            return None
    
    async def get_strategy_balance(self, strategy_id: str) -> Optional[Dict[str, Any]]:
        """Get balance data for a specific strategy from Redis"""
        try:
            if not self.redis_client:
                return None
            
            # Get balance data from Redis
            balance_key = f"strategy_balance:{strategy_id}"
            balance_data = await self.redis_client.hgetall(balance_key)
            
            if not balance_data:
                return None
            
            # Convert string values to appropriate types
            return {
                "strategy_id": strategy_id,
                "balance": float(balance_data.get("balance", 0)),
                "available": float(balance_data.get("available", 0)),
                "margin_used": float(balance_data.get("margin_used", 0)),
                "realized_pnl": float(balance_data.get("realized_pnl", 0)),
                "daily_pnl": float(balance_data.get("daily_pnl", 0)),
                "weekly_pnl": float(balance_data.get("weekly_pnl", 0)),
                "monthly_pnl": float(balance_data.get("monthly_pnl", 0)),
                "total_trades": int(balance_data.get("total_trades", 0)),
                "total_volume": float(balance_data.get("total_volume", 0)),
                "last_updated": balance_data.get("last_updated", ""),
                "broker": balance_data.get("broker", "mexc"),
                "account_id": balance_data.get("account_id", "")
            }
            
        except Exception as e:
            logger.error(f"❌ Error getting strategy balance for {strategy_id}: {e}")
            return None

# Global data logger instance
data_logger = DataLogger()
