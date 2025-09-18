"""
Advanced features for the Risk Management System
Order book simulation, latency monitoring, and enhanced risk metrics
"""
import random
import time
from datetime import datetime, timedelta
from typing import Dict, List, Tuple
from dataclasses import dataclass, field
from enum import Enum

@dataclass
class LatencyMetrics:
    broker: str
    avg_latency_ms: float
    p95_latency_ms: float
    p99_latency_ms: float
    last_update: datetime
    
@dataclass
class MarketData:
    symbol: str
    bid: float
    ask: float
    last_price: float
    volume: float
    timestamp: datetime
    spread_bps: float = field(init=False)
    
    def __post_init__(self):
        self.spread_bps = ((self.ask - self.bid) / self.last_price) * 10000

class OrderBookSimulator:
    def __init__(self):
        self.order_books = {}
        self.market_data = {}
        
    def initialize_symbols(self, symbols: List[str]):
        for symbol in symbols:
            # Initialize with random market data
            base_price = random.uniform(10, 1000)
            spread = base_price * random.uniform(0.0001, 0.001)  # 1-10 bps spread
            
            self.market_data[symbol] = MarketData(
                symbol=symbol,
                bid=base_price - spread/2,
                ask=base_price + spread/2,
                last_price=base_price,
                volume=random.uniform(1000, 100000),
                timestamp=datetime.now()
            )
            
    def update_market_data(self):
        """Simulate real-time market data updates"""
        for symbol, data in self.market_data.items():
            # Random price movement
            change_pct = random.uniform(-0.001, 0.001)  # ±0.1% max move
            new_price = data.last_price * (1 + change_pct)
            
            # Update bid/ask around new price
            spread = new_price * random.uniform(0.0001, 0.001)
            data.bid = new_price - spread/2
            data.ask = new_price + spread/2
            data.last_price = new_price
            data.volume += random.uniform(100, 1000)
            data.timestamp = datetime.now()
            
            # Recalculate spread
            data.spread_bps = ((data.ask - data.bid) / data.last_price) * 10000

class LatencyMonitor:
    def __init__(self):
        self.latency_data = {}
        self.order_timestamps = {}
        
    def record_order_sent(self, order_id: str, broker: str):
        self.order_timestamps[order_id] = {
            'sent_time': time.time(),
            'broker': broker
        }
        
    def record_order_ack(self, order_id: str):
        if order_id in self.order_timestamps:
            sent_time = self.order_timestamps[order_id]['sent_time']
            broker = self.order_timestamps[order_id]['broker']
            
            latency_ms = (time.time() - sent_time) * 1000
            
            if broker not in self.latency_data:
                self.latency_data[broker] = []
            
            self.latency_data[broker].append(latency_ms)
            
            # Keep only last 1000 measurements
            if len(self.latency_data[broker]) > 1000:
                self.latency_data[broker] = self.latency_data[broker][-1000:]
                
    def get_latency_metrics(self, broker: str) -> LatencyMetrics:
        if broker not in self.latency_data or not self.latency_data[broker]:
            return LatencyMetrics(broker, 0, 0, 0, datetime.now())
            
        latencies = sorted(self.latency_data[broker])
        
        avg_latency = sum(latencies) / len(latencies)
        p95_latency = latencies[int(len(latencies) * 0.95)]
        p99_latency = latencies[int(len(latencies) * 0.99)]
        
        return LatencyMetrics(
            broker=broker,
            avg_latency_ms=avg_latency,
            p95_latency_ms=p95_latency,
            p99_latency_ms=p99_latency,
            last_update=datetime.now()
        )

class RiskMetrics:
    def __init__(self):
        self.exposure_by_asset = {}
        self.exposure_by_broker = {}
        self.var_95 = 0
        self.var_99 = 0
        self.sharpe_ratio = 0
        self.max_position_size = 0
        self.concentration_risk = 0
        
    def update_exposures(self, orders: List):
        """Calculate current exposures across assets and brokers"""
        self.exposure_by_asset.clear()
        self.exposure_by_broker.clear()
        
        for order in orders:
            if order.status.value == "Filled":
                notional = order.quantity * order.fill_price if order.fill_price else order.quantity * order.price
                
                # Asset exposure
                if order.asset_class.value not in self.exposure_by_asset:
                    self.exposure_by_asset[order.asset_class.value] = 0
                self.exposure_by_asset[order.asset_class.value] += notional
                
                # Broker exposure
                if order.broker not in self.exposure_by_broker:
                    self.exposure_by_broker[order.broker] = 0
                self.exposure_by_broker[order.broker] += notional
                
        # Calculate concentration risk (% of total exposure in largest position)
        total_exposure = sum(self.exposure_by_asset.values())
        if total_exposure > 0:
            max_exposure = max(self.exposure_by_asset.values()) if self.exposure_by_asset else 0
            self.concentration_risk = (max_exposure / total_exposure) * 100
            
    def calculate_var(self, pnl_history: List[float], confidence_level: float = 0.95):
        """Calculate Value at Risk"""
        if len(pnl_history) < 30:  # Need minimum data points
            return 0
            
        sorted_pnl = sorted(pnl_history)
        var_index = int((1 - confidence_level) * len(sorted_pnl))
        return abs(sorted_pnl[var_index]) if var_index < len(sorted_pnl) else 0

class AlertSystem:
    def __init__(self):
        self.alerts = []
        self.thresholds = {
            'max_daily_loss': -50000,
            'max_concentration': 30,  # 30%
            'max_latency_ms': 100,
            'min_fill_rate': 85,  # 85%
            'max_rejected_orders': 50
        }
        
    def check_alerts(self, risk_metrics, latency_metrics, broker_stats):
        """Check various risk thresholds and generate alerts"""
        new_alerts = []
        
        # Daily loss alert
        daily_pnl = getattr(risk_metrics, 'daily_pnl', 0)
        if daily_pnl < self.thresholds['max_daily_loss']:
            new_alerts.append({
                'level': 'CRITICAL',
                'message': f"Daily loss threshold breached: ${daily_pnl:,.2f}",
                'timestamp': datetime.now()
            })
            
        # Concentration risk alert
        if risk_metrics.concentration_risk > self.thresholds['max_concentration']:
            new_alerts.append({
                'level': 'WARNING',
                'message': f"High concentration risk: {risk_metrics.concentration_risk:.1f}%",
                'timestamp': datetime.now()
            })
            
        # Latency alerts
        for broker, metrics in latency_metrics.items():
            if metrics.p95_latency_ms > self.thresholds['max_latency_ms']:
                new_alerts.append({
                    'level': 'WARNING',
                    'message': f"High latency for {broker}: {metrics.p95_latency_ms:.1f}ms",
                    'timestamp': datetime.now()
                })
                
        # Broker performance alerts
        for broker, stats in broker_stats.items():
            if stats['total'] > 0:
                fill_rate = (stats['filled'] / stats['total']) * 100
                if fill_rate < self.thresholds['min_fill_rate']:
                    new_alerts.append({
                        'level': 'WARNING',
                        'message': f"Low fill rate for {broker}: {fill_rate:.1f}%",
                        'timestamp': datetime.now()
                    })
                    
                if stats['rejected'] > self.thresholds['max_rejected_orders']:
                    new_alerts.append({
                        'level': 'WARNING',
                        'message': f"High rejection count for {broker}: {stats['rejected']}",
                        'timestamp': datetime.now()
                    })
        
        # Add new alerts and keep only recent ones (last 100)
        self.alerts.extend(new_alerts)
        self.alerts = self.alerts[-100:]
        
        return new_alerts

class PerformanceAnalyzer:
    def __init__(self):
        self.trade_analysis = {}
        
    def analyze_trading_performance(self, orders):
        """Analyze trading performance metrics"""
        filled_orders = [o for o in orders if o.status.value == "Filled"]
        
        if not filled_orders:
            return {}
            
        # Calculate various performance metrics
        total_trades = len(filled_orders)
        
        # Win rate calculation (simplified)
        profitable_trades = sum(1 for o in filled_orders if random.random() > 0.4)  # Mock profitability
        win_rate = (profitable_trades / total_trades) * 100 if total_trades > 0 else 0
        
        # Average trade size
        avg_trade_size = sum(o.quantity * (o.fill_price or o.price) for o in filled_orders) / total_trades
        
        # Trades per asset class
        asset_distribution = {}
        for order in filled_orders:
            asset = order.asset_class.value
            asset_distribution[asset] = asset_distribution.get(asset, 0) + 1
            
        return {
            'total_trades': total_trades,
            'win_rate': win_rate,
            'avg_trade_size': avg_trade_size,
            'asset_distribution': asset_distribution,
            'most_active_asset': max(asset_distribution.keys(), key=asset_distribution.get) if asset_distribution else 'N/A'
        }
