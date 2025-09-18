"""
GUI Data Service - Real-time data integration for the trading GUI
Connects the GUI to real COM system data instead of mock data
"""
import asyncio
import logging
import time
import queue
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from enum import Enum
import json

logger = logging.getLogger(__name__)

class AssetClass(Enum):
    CRYPTO = "Crypto"
    STOCKS = "Stocks"
    FOREX = "Forex"
    FUTURES = "Futures"
    COMMODITIES = "Commodities"
    BONDS = "Bonds"

class OrderStatus(Enum):
    QUEUED = "Queued"
    SENT = "Sent"
    FILLED = "Filled"
    CANCELLED = "Cancelled"
    REJECTED = "Rejected"

class OrderSide(Enum):
    BUY = "BUY"
    SELL = "SELL"

@dataclass
class Order:
    id: str
    symbol: str
    asset_class: AssetClass
    side: OrderSide
    quantity: float
    price: float
    broker: str
    status: OrderStatus
    timestamp: datetime
    fill_price: Optional[float] = None
    fill_time: Optional[datetime] = None

class RealDataService:
    """Service that provides real COM data to the GUI"""
    
    def __init__(self):
        self.orders = []
        self.order_queue = queue.Queue()
        self.positions = {}
        self.running = False
        
        # Metrics
        self.metrics = {
            'orders_per_minute': 0,
            'queued_orders': 0,
            'sent_orders': 0,
            'filled_orders': 0,
            'rejected_orders': 0,
            'total_orders': 0
        }
        
        self.broker_metrics = {}
        self.asset_metrics = {}
        
        # Risk metrics
        self.daily_pnl = 0.0
        self.total_pnl = 0.0
        self.max_drawdown = 0.0
        self.total_volume = 0.0
        
        # Symbol mapping for asset classes
        self.symbol_asset_mapping = {
            # Crypto
            'BTC_USDT': AssetClass.CRYPTO, 'ETH_USDT': AssetClass.CRYPTO,
            'ADA_USDT': AssetClass.CRYPTO, 'SOL_USDT': AssetClass.CRYPTO,
            'DOT_USDT': AssetClass.CRYPTO, 'LINK_USDT': AssetClass.CRYPTO,
            'BNB_USDT': AssetClass.CRYPTO, 'XRP_USDT': AssetClass.CRYPTO,
            'MATIC_USDT': AssetClass.CRYPTO, 'AVAX_USDT': AssetClass.CRYPTO,
            'ATOM_USDT': AssetClass.CRYPTO, 'LTC_USDT': AssetClass.CRYPTO,
            'UNI_USDT': AssetClass.CRYPTO, 'FIL_USDT': AssetClass.CRYPTO,
            'TRX_USDT': AssetClass.CRYPTO, 'ETC_USDT': AssetClass.CRYPTO,
            'XLM_USDT': AssetClass.CRYPTO, 'VET_USDT': AssetClass.CRYPTO,
            'ICP_USDT': AssetClass.CRYPTO, 'FTM_USDT': AssetClass.CRYPTO,
            'HBAR_USDT': AssetClass.CRYPTO, 'NEAR_USDT': AssetClass.CRYPTO,
            'SAND_USDT': AssetClass.CRYPTO, 'MANA_USDT': AssetClass.CRYPTO,
            'DOGE_USDT': AssetClass.CRYPTO,
        }
        
        # Broker mapping
        self.broker_mapping = {
            'mexc': 'MEXC',
            'binance': 'Binance',
            'coinbase': 'Coinbase Pro',
            'kraken': 'Kraken',
            'bitfinex': 'Bitfinex',
            'kucoin': 'KuCoin',
            'gate': 'Gate.io',
            'huobi': 'Huobi',
            'okx': 'OKX',
            'bybit': 'Bybit',
        }
    
    def start(self):
        """Start the real data service"""
        self.running = True
        logger.info("🚀 Real data service started")
    
    def stop(self):
        """Stop the real data service"""
        self.running = False
        logger.info("🛑 Real data service stopped")
    
    def add_real_order(self, order_data: Dict[str, Any]):
        """Add a real order from COM system"""
        try:
            # Extract data from COM order
            symbol = order_data.get('symbol', 'UNKNOWN')
            side = OrderSide.BUY if order_data.get('side') == 'BUY' else OrderSide.SELL
            quantity = float(order_data.get('quantity', 0))
            price = float(order_data.get('price', 0))
            broker = self.broker_mapping.get(order_data.get('broker', 'mexc'), 'MEXC')
            
            # Determine asset class
            asset_class = self.symbol_asset_mapping.get(symbol, AssetClass.CRYPTO)
            
            # Create GUI order
            gui_order = Order(
                id=order_data.get('order_ref', f"ORD_{int(time.time() * 1000000) % 1000000}"),
                symbol=symbol,
                asset_class=asset_class,
                side=side,
                quantity=quantity,
                price=price,
                broker=broker,
                status=OrderStatus.QUEUED,
                timestamp=datetime.now()
            )
            
            # Add to queue for processing
            self.order_queue.put(gui_order)
            self.orders.append(gui_order)
            
            logger.info(f"📊 Added real order: {symbol} {side.value} {quantity} @ {price}")
            
        except Exception as e:
            logger.error(f"Error adding real order: {e}")
    
    def update_order_status(self, order_id: str, status: str, fill_price: Optional[float] = None):
        """Update order status from COM system"""
        try:
            # Find the order
            for order in self.orders:
                if order.id == order_id:
                    # Map COM status to GUI status
                    if status == 'FILLED':
                        order.status = OrderStatus.FILLED
                        if fill_price:
                            order.fill_price = fill_price
                            order.fill_time = datetime.now()
                    elif status == 'CANCELLED':
                        order.status = OrderStatus.CANCELLED
                    elif status == 'REJECTED':
                        order.status = OrderStatus.REJECTED
                    elif status == 'SENT':
                        order.status = OrderStatus.SENT
                    
                    logger.info(f"📋 Updated order {order_id}: {status}")
                    break
                    
        except Exception as e:
            logger.error(f"Error updating order status: {e}")
    
    def update_position_data(self, position_data: Dict[str, Any]):
        """Update position data from COM system"""
        try:
            position_id = position_data.get('position_id')
            if position_id:
                self.positions[position_id] = position_data
                
                # Update P&L metrics
                unrealized_pnl = position_data.get('unrealized_pnl', 0.0)
                self.total_pnl += unrealized_pnl
                self.daily_pnl += unrealized_pnl
                
                # Update max drawdown
                if self.total_pnl < self.max_drawdown:
                    self.max_drawdown = self.total_pnl
                
                logger.info(f"📊 Updated position {position_id}: P&L {unrealized_pnl}")
                
        except Exception as e:
            logger.error(f"Error updating position data: {e}")
    
    def get_orders(self) -> List[Order]:
        """Get all orders for GUI display"""
        return self.orders
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get current metrics for GUI display"""
        # Calculate orders per minute
        now = datetime.now()
        recent_orders = [o for o in self.orders if (now - o.timestamp).total_seconds() < 60]
        self.metrics['orders_per_minute'] = len(recent_orders)
        
        # Count orders by status
        self.metrics['queued_orders'] = len([o for o in self.orders if o.status == OrderStatus.QUEUED])
        self.metrics['sent_orders'] = len([o for o in self.orders if o.status == OrderStatus.SENT])
        self.metrics['filled_orders'] = len([o for o in self.orders if o.status == OrderStatus.FILLED])
        self.metrics['rejected_orders'] = len([o for o in self.orders if o.status == OrderStatus.REJECTED])
        self.metrics['total_orders'] = len(self.orders)
        
        return self.metrics
    
    def get_broker_queues(self) -> Dict[str, int]:
        """Get broker queue counts"""
        broker_queues = {}
        for order in self.orders:
            if order.status in [OrderStatus.QUEUED, OrderStatus.SENT]:
                broker_queues[order.broker] = broker_queues.get(order.broker, 0) + 1
        return broker_queues
    
    def get_broker_performance(self) -> Dict[str, Dict[str, Any]]:
        """Get broker performance metrics"""
        broker_stats = {}
        for order in self.orders:
            broker = order.broker
            if broker not in broker_stats:
                broker_stats[broker] = {'total': 0, 'filled': 0, 'rejected': 0}
            
            broker_stats[broker]['total'] += 1
            if order.status == OrderStatus.FILLED:
                broker_stats[broker]['filled'] += 1
            elif order.status == OrderStatus.REJECTED:
                broker_stats[broker]['rejected'] += 1
        
        return broker_stats
    
    def get_asset_performance(self) -> Dict[str, int]:
        """Get asset class performance metrics"""
        asset_stats = {}
        for order in self.orders:
            asset_class = order.asset_class.value
            asset_stats[asset_class] = asset_stats.get(asset_class, 0) + 1
        return asset_stats
    
    def get_risk_metrics(self) -> Dict[str, float]:
        """Get risk metrics"""
        return {
            'total_pnl': self.total_pnl,
            'daily_pnl': self.daily_pnl,
            'max_drawdown': self.max_drawdown,
            'total_volume': self.total_volume
        }
    
    def get_recent_trades(self, count: int = 10) -> List[Order]:
        """Get recent trades for ticker display"""
        return sorted(self.orders[-count:], key=lambda x: x.timestamp, reverse=True)

# Global instance
real_data_service = RealDataService()
