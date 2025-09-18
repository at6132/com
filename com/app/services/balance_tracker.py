"""
Balance and Performance Tracking Service
Periodically logs account balances, total balances, and performance metrics
"""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
import time

logger = logging.getLogger(__name__)

class BalanceTracker:
    """Tracks and logs account balances and performance metrics"""
    
    def __init__(self):
        self.running = False
        self.data_logger = None
        self.position_tracker = None
        self.broker_manager = None
        
        # Performance tracking
        self.performance_metrics = {}
        self.daily_pnl_start = {}
        self.weekly_pnl_start = {}
        self.monthly_pnl_start = {}
        
        # Timing controls - initialize to current time to prevent immediate execution
        import time
        current_time = time.time()
        self.last_account_balance_update = current_time  # Track last account balance update
        self.last_total_balance_update = current_time    # Track last total balance update
        self.last_performance_update_time = current_time # Track last performance update
        
    async def start_tracking(self):
        """Start balance tracking service"""
        if self.running:
            return
        
        self.running = True
        logger.info("🔄 Starting balance tracking service...")
        
        # Import dependencies
        from .data_logger import data_logger
        from .position_tracker import position_tracker
        from ..adapters.manager import broker_manager
        
        self.data_logger = data_logger
        self.position_tracker = position_tracker
        self.broker_manager = broker_manager
        
        # Start tracking loop
        asyncio.create_task(self._tracking_loop())
        logger.info("✅ Balance tracking service started")
    
    async def stop_tracking(self):
        """Stop balance tracking service"""
        self.running = False
        logger.info("🛑 Balance tracking service stopped")
    
    async def _tracking_loop(self):
        """Main tracking loop"""
        while self.running:
            try:
                current_time = time.time()
                
                # Log account balances every 5 minutes (300 seconds)
                if current_time - self.last_account_balance_update >= 300:
                    await self._log_account_balances()
                    self.last_account_balance_update = current_time
                
                # Log total balance every 5 minutes (same as account balances)
                if current_time - self.last_total_balance_update >= 300:
                    await self._log_total_balance()
                    self.last_total_balance_update = current_time
                
                # Log performance metrics every minute (60 seconds)
                if current_time - self.last_performance_update_time >= 60:
                    await self._log_performance_metrics()
                    self.last_performance_update_time = current_time
                
                # Wait 10 seconds before next iteration
                await asyncio.sleep(10)
                
            except Exception as e:
                logger.error(f"❌ Error in balance tracking loop: {e}")
                await asyncio.sleep(10)
    
    async def _log_account_balances(self):
        """Log individual account balances every 5 minutes"""
        try:
            # Get all active positions from position tracker
            if not self.position_tracker:
                return
            
            # Group positions by strategy/account
            account_positions = {}
            for position_id, position in self.position_tracker.positions.items():
                if position.status.value == "OPEN":
                    strategy_id = position.strategy_id
                    if strategy_id not in account_positions:
                        account_positions[strategy_id] = []
                    account_positions[strategy_id].append(position)
            
            # Calculate balances for each account
            for strategy_id, positions in account_positions.items():
                balance_data = await self._calculate_account_balance(strategy_id, positions)
                await self.data_logger.log_account_balance(strategy_id, balance_data)
                
        except Exception as e:
            logger.error(f"❌ Error logging account balances: {e}")
    
    async def _log_total_balance(self):
        """Log total balance aggregation every 10 seconds"""
        try:
            if not self.position_tracker:
                return
            
            # Calculate total metrics
            total_data = await self._calculate_total_balance()
            await self.data_logger.log_total_balance(total_data)
            
        except Exception as e:
            logger.error(f"❌ Error logging total balance: {e}")
    
    async def _log_performance_metrics(self):
        """Log performance metrics every minute"""
        try:
            # Get historical data for performance calculations
            for strategy_id in self.performance_metrics.keys():
                performance_data = await self._calculate_strategy_performance(strategy_id)
                # Log to performance CSV
                await self._log_strategy_performance(strategy_id, performance_data)
                
        except Exception as e:
            logger.error(f"❌ Error logging performance metrics: {e}")
    
    async def _calculate_account_balance(self, strategy_id: str, positions: List) -> Dict[str, Any]:
        """Calculate account balance and metrics using real MEXC data"""
        try:
            # Get real MEXC balance data
            mexc_balances = {}
            if self.broker_manager:
                try:
                    # Get MEXC broker instance
                    mexc_broker = self.broker_manager.get_adapter("mexc")
                    if mexc_broker:
                        mexc_balances = await mexc_broker.get_balances()
                        logger.info(f"📊 Retrieved MEXC balances: {mexc_balances}")
                except Exception as e:
                    logger.error(f"❌ Error getting MEXC balances: {e}")
            
            # Get historical orders for this strategy
            orders = await self.data_logger.get_historical_data("orders", strategy_id)
            
            # Calculate metrics from historical data
            total_pnl = 0.0
            realized_pnl = 0.0
            total_trades = len(orders)
            winning_trades = 0
            losing_trades = 0
            total_volume = 0.0
            
            # Process orders
            for order in orders:
                if order.get('pnl'):
                    pnl = float(order['pnl'])
                    total_pnl += pnl
                    realized_pnl += pnl
                    total_volume += float(order.get('quantity', 0)) * float(order.get('price', 0))
                    
                    if pnl > 0:
                        winning_trades += 1
                    elif pnl < 0:
                        losing_trades += 1
            
            # Calculate unrealized PnL from current positions
            unrealized_pnl = 0.0
            margin_used = 0.0
            for position in positions:
                unrealized_pnl += position.unrealized_pnl
                margin_used += position.margin_used
            
            # Get real balance data from MEXC
            total_balance = 0.0
            available_balance = 0.0
            
            if mexc_balances:
                # Sum up all USDT balances (assuming USDT is the main trading currency)
                total_balance = mexc_balances.get('USDT', 0.0)
                available_balance = mexc_balances.get('USDT', 0.0)  # MEXC returns available balance
                
                # Add other currencies if needed
                for currency, balance in mexc_balances.items():
                    if currency != 'USDT' and balance > 0:
                        # Convert to USDT equivalent (simplified - would need real conversion rates)
                        total_balance += balance * 0.1  # Placeholder conversion
                        available_balance += balance * 0.1
            else:
                # Fallback to calculated values if MEXC data unavailable
                total_balance = 10000 + total_pnl  # Starting balance + PnL
                available_balance = 10000 + total_pnl - margin_used
            
            # Calculate daily PnL
            today = datetime.utcnow().date()
            daily_orders = [o for o in orders if datetime.fromisoformat(o['timestamp']).date() == today]
            daily_pnl = sum(float(o.get('pnl', 0)) for o in daily_orders if o.get('pnl'))
            
            # Calculate weekly PnL
            week_start = today - timedelta(days=today.weekday())
            weekly_orders = [o for o in orders if datetime.fromisoformat(o['timestamp']).date() >= week_start]
            weekly_pnl = sum(float(o.get('pnl', 0)) for o in weekly_orders if o.get('pnl'))
            
            # Calculate monthly PnL
            month_start = today.replace(day=1)
            monthly_orders = [o for o in orders if datetime.fromisoformat(o['timestamp']).date() >= month_start]
            monthly_pnl = sum(float(o.get('pnl', 0)) for o in monthly_orders if o.get('pnl'))
            
            # Calculate win rate
            win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
            
            # Calculate average win/loss
            winning_pnls = [float(o['pnl']) for o in orders if o.get('pnl') and float(o['pnl']) > 0]
            losing_pnls = [float(o['pnl']) for o in orders if o.get('pnl') and float(o['pnl']) < 0]
            
            avg_win = sum(winning_pnls) / len(winning_pnls) if winning_pnls else 0
            avg_loss = sum(losing_pnls) / len(losing_pnls) if losing_pnls else 0
            
            # Calculate profit factor
            gross_profit = sum(winning_pnls) if winning_pnls else 0
            gross_loss = abs(sum(losing_pnls)) if losing_pnls else 0
            profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf') if gross_profit > 0 else 0
            
            # Calculate max drawdown (simplified)
            max_drawdown = 0.0
            max_drawdown_percent = 0.0
            if total_trades > 0:
                # This is a simplified calculation - in reality you'd track peak equity
                pnl_values = [float(o.get('pnl', 0)) for o in orders if o.get('pnl')]
                if pnl_values:
                    max_drawdown = min(0, min(pnl_values))
                    max_drawdown_percent = (max_drawdown / total_balance) * 100 if total_balance > 0 else 0
            
            return {
                'strategy_id': strategy_id,
                'total_balance': total_balance,
                'available_balance': available_balance,
                'margin_used': margin_used,
                'unrealized_pnl': unrealized_pnl,
                'realized_pnl': realized_pnl,
                'total_pnl': total_pnl,
                'daily_pnl': daily_pnl,
                'weekly_pnl': weekly_pnl,
                'monthly_pnl': monthly_pnl,
                'max_drawdown': max_drawdown,
                'max_drawdown_percent': max_drawdown_percent,
                'win_rate': win_rate,
                'total_trades': total_trades,
                'winning_trades': winning_trades,
                'losing_trades': losing_trades,
                'avg_win': avg_win,
                'avg_loss': avg_loss,
                'profit_factor': profit_factor,
                'sharpe_ratio': 0.0,  # Would need more complex calculation
                'total_volume': total_volume
            }
            
        except Exception as e:
            logger.error(f"❌ Error calculating account balance: {e}")
            return {}
    
    async def _calculate_total_balance(self) -> Dict[str, Any]:
        """Calculate total balance across all accounts using real MEXC data"""
        try:
            # Get real MEXC balance data
            mexc_balances = {}
            if self.broker_manager:
                try:
                    # Get MEXC broker instance
                    mexc_broker = self.broker_manager.get_adapter("mexc")
                    if mexc_broker:
                        mexc_balances = await mexc_broker.get_balances()
                        logger.info(f"📊 Retrieved MEXC total balances: {mexc_balances}")
                except Exception as e:
                    logger.error(f"❌ Error getting MEXC total balances: {e}")
            
            # Initialize totals
            total_balance = 0.0
            total_available = 0.0
            total_margin_used = 0.0
            total_unrealized_pnl = 0.0
            total_realized_pnl = 0.0
            total_daily_pnl = 0.0
            total_weekly_pnl = 0.0
            total_monthly_pnl = 0.0
            total_trades = 0
            total_volume = 0.0
            active_positions = 0
            active_strategies = set()
            active_accounts = set()
            
            # Get real balance data from MEXC
            if mexc_balances:
                # Sum up all USDT balances (assuming USDT is the main trading currency)
                total_balance = mexc_balances.get('USDT', 0.0)
                total_available = mexc_balances.get('USDT', 0.0)  # MEXC returns available balance
                
                # Add other currencies if needed
                for currency, balance in mexc_balances.items():
                    if currency != 'USDT' and balance > 0:
                        # Convert to USDT equivalent (simplified - would need real conversion rates)
                        total_balance += balance * 0.1  # Placeholder conversion
                        total_available += balance * 0.1
            
            # Get all positions
            if self.position_tracker:
                for position_id, position in self.position_tracker.positions.items():
                    if position.status.value == "OPEN":
                        active_positions += 1
                        active_strategies.add(position.strategy_id)
                        active_accounts.add(position.strategy_id)  # Using strategy_id as account_id for now
                        total_unrealized_pnl += position.unrealized_pnl
                        total_margin_used += position.margin_used
            
            # Get all orders for total calculations
            all_orders = await self.data_logger.get_historical_data("orders")
            
            for order in all_orders:
                if order.get('pnl'):
                    total_realized_pnl += float(order['pnl'])
                    total_volume += float(order.get('quantity', 0)) * float(order.get('price', 0))
                    total_trades += 1
                    
                    # Daily PnL
                    order_time = datetime.fromisoformat(order['timestamp'])
                    if order_time.date() == datetime.utcnow().date():
                        total_daily_pnl += float(order['pnl'])
                    
                    # Weekly PnL
                    week_start = datetime.utcnow().date() - timedelta(days=datetime.utcnow().weekday())
                    if order_time.date() >= week_start:
                        total_weekly_pnl += float(order['pnl'])
                    
                    # Monthly PnL
                    month_start = datetime.utcnow().date().replace(day=1)
                    if order_time.date() >= month_start:
                        total_monthly_pnl += float(order['pnl'])
            
            # If no MEXC data available, use calculated values
            if not mexc_balances:
                total_balance = 10000 * len(active_accounts) + total_realized_pnl + total_unrealized_pnl
                total_available = total_balance - total_margin_used
            
            # Calculate max drawdown (simplified)
            total_max_drawdown = 0.0
            total_max_drawdown_percent = 0.0
            if total_trades > 0:
                all_pnl_values = [float(o.get('pnl', 0)) for o in all_orders if o.get('pnl')]
                if all_pnl_values:
                    total_max_drawdown = min(0, min(all_pnl_values))
                    total_max_drawdown_percent = (total_max_drawdown / total_balance) * 100 if total_balance > 0 else 0
            
            return {
                'total_balance': total_balance,
                'total_available': total_available,
                'total_margin_used': total_margin_used,
                'total_unrealized_pnl': total_unrealized_pnl,
                'total_realized_pnl': total_realized_pnl,
                'total_daily_pnl': total_daily_pnl,
                'total_weekly_pnl': total_weekly_pnl,
                'total_monthly_pnl': total_monthly_pnl,
                'total_max_drawdown': total_max_drawdown,
                'total_max_drawdown_percent': total_max_drawdown_percent,
                'total_trades': total_trades,
                'total_volume': total_volume,
                'active_positions': active_positions,
                'active_strategies': len(active_strategies),
                'active_accounts': len(active_accounts)
            }
            
        except Exception as e:
            logger.error(f"❌ Error calculating total balance: {e}")
            return {}
    
    async def _calculate_strategy_performance(self, strategy_id: str) -> Dict[str, Any]:
        """Calculate detailed performance metrics for a strategy"""
        try:
            # Get historical data
            orders = await self.data_logger.get_historical_data("orders", strategy_id)
            positions = await self.data_logger.get_historical_data("positions", strategy_id)
            
            # Calculate metrics
            total_pnl = sum(float(o.get('pnl', 0)) for o in orders if o.get('pnl'))
            total_trades = len(orders)
            winning_trades = len([o for o in orders if o.get('pnl') and float(o['pnl']) > 0])
            losing_trades = len([o for o in orders if o.get('pnl') and float(o['pnl']) < 0])
            
            win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
            
            # Calculate daily/weekly/monthly PnL
            today = datetime.utcnow().date()
            daily_pnl = sum(float(o.get('pnl', 0)) for o in orders 
                          if o.get('pnl') and datetime.fromisoformat(o['timestamp']).date() == today)
            
            week_start = today - timedelta(days=today.weekday())
            weekly_pnl = sum(float(o.get('pnl', 0)) for o in orders 
                           if o.get('pnl') and datetime.fromisoformat(o['timestamp']).date() >= week_start)
            
            month_start = today.replace(day=1)
            monthly_pnl = sum(float(o.get('pnl', 0)) for o in orders 
                            if o.get('pnl') and datetime.fromisoformat(o['timestamp']).date() >= month_start)
            
            # Calculate other metrics
            total_volume = sum(float(o.get('quantity', 0)) * float(o.get('price', 0)) for o in orders)
            active_positions = len([p for p in positions if p.get('status') == 'OPEN'])
            
            # Calculate average position duration
            closed_positions = [p for p in positions if p.get('status') == 'CLOSED' and p.get('duration_seconds')]
            avg_duration = sum(float(p['duration_seconds']) for p in closed_positions) / len(closed_positions) if closed_positions else 0
            
            # Calculate best/worst trades
            pnls = [float(o['pnl']) for o in orders if o.get('pnl')]
            best_trade = max(pnls) if pnls else 0
            worst_trade = min(pnls) if pnls else 0
            
            return {
                'strategy_id': strategy_id,
                'total_pnl': total_pnl,
                'daily_pnl': daily_pnl,
                'weekly_pnl': weekly_pnl,
                'monthly_pnl': monthly_pnl,
                'max_drawdown': 0.0,  # Would need more complex calculation
                'max_drawdown_percent': 0.0,
                'win_rate': win_rate,
                'total_trades': total_trades,
                'winning_trades': winning_trades,
                'losing_trades': losing_trades,
                'avg_win': 0.0,  # Would calculate from winning trades
                'avg_loss': 0.0,  # Would calculate from losing trades
                'profit_factor': 0.0,  # Would calculate from wins/losses
                'sharpe_ratio': 0.0,  # Would need more complex calculation
                'total_volume': total_volume,
                'active_positions': active_positions,
                'avg_position_duration': avg_duration,
                'best_trade': best_trade,
                'worst_trade': worst_trade,
                'consecutive_wins': 0,  # Would track this
                'consecutive_losses': 0  # Would track this
            }
            
        except Exception as e:
            logger.error(f"❌ Error calculating strategy performance: {e}")
            return {}
    
    async def _log_strategy_performance(self, strategy_id: str, performance_data: Dict[str, Any]):
        """Log strategy performance to CSV"""
        try:
            # Create performance CSV if it doesn't exist
            performance_csv = self.data_logger.base_dir / "performance" / f"strategy_{strategy_id}_performance.csv"
            
            if not performance_csv.exists():
                with open(performance_csv, 'w', newline='') as f:
                    import csv
                    writer = csv.writer(f)
                    writer.writerow([
                        'timestamp', 'strategy_id', 'total_pnl', 'daily_pnl', 'weekly_pnl', 'monthly_pnl',
                        'max_drawdown', 'max_drawdown_percent', 'win_rate', 'total_trades', 'winning_trades',
                        'losing_trades', 'avg_win', 'avg_loss', 'profit_factor', 'sharpe_ratio',
                        'total_volume', 'active_positions', 'avg_position_duration', 'best_trade',
                        'worst_trade', 'consecutive_wins', 'consecutive_losses'
                    ])
            
            # Add timestamp and log
            performance_data['timestamp'] = datetime.utcnow().isoformat()
            await self.data_logger._write_to_csv(performance_csv, performance_data)
            
        except Exception as e:
            logger.error(f"❌ Error logging strategy performance: {e}")
    
    async def get_strategy_balance(self, strategy_id: str) -> Optional[Dict[str, Any]]:
        """Get balance data for a specific strategy/algo"""
        try:
            if not self.data_logger:
                return None
            
            # Get the latest balance data from Redis or CSV
            balance_data = await self.data_logger.get_strategy_balance(strategy_id)
            
            if not balance_data:
                return None
            
            # Get additional data from position tracker
            positions = self.position_tracker.get_positions_by_strategy(strategy_id) if self.position_tracker else []
            active_positions = len([p for p in positions if p.status == "OPEN"])
            
            # Calculate unrealized PnL from active positions
            unrealized_pnl = sum(
                (p.current_price - p.entry_price) * p.size * (1 if p.side == "LONG" else -1)
                for p in positions if p.status == "OPEN"
            )
            
            return {
                "strategy_id": strategy_id,
                "balance": balance_data.get("balance", 0.0),
                "available": balance_data.get("available", 0.0),
                "margin_used": balance_data.get("margin_used", 0.0),
                "unrealized_pnl": unrealized_pnl,
                "realized_pnl": balance_data.get("realized_pnl", 0.0),
                "daily_pnl": balance_data.get("daily_pnl", 0.0),
                "weekly_pnl": balance_data.get("weekly_pnl", 0.0),
                "monthly_pnl": balance_data.get("monthly_pnl", 0.0),
                "active_positions": active_positions,
                "total_trades": balance_data.get("total_trades", 0),
                "total_volume": balance_data.get("total_volume", 0.0),
                "last_updated": balance_data.get("last_updated", ""),
                "broker": balance_data.get("broker", "mexc"),
                "account_id": balance_data.get("account_id", "")
            }
            
        except Exception as e:
            logger.error(f"❌ Error getting strategy balance for {strategy_id}: {e}")
            return None
    
    async def get_total_balance(self) -> Dict[str, Any]:
        """Get total balance across all strategies"""
        try:
            if not self.broker_manager:
                return {}
            
            # Get real MEXC balance data
            mexc_balances = {}
            try:
                mexc_broker = self.broker_manager.get_adapter("mexc")
                if mexc_broker:
                    mexc_balances = await mexc_broker.get_balances()
                    logger.info(f"📊 Retrieved MEXC total balances: {mexc_balances}")
            except Exception as e:
                logger.error(f"❌ Error getting MEXC total balances: {e}")
            
            # Calculate totals
            total_balance = mexc_balances.get('USDT', 0.0)
            total_available = mexc_balances.get('USDT', 0.0)
            
            # Get all positions for unrealized PnL calculation
            all_positions = self.position_tracker.get_all_positions() if self.position_tracker else []
            active_positions = [p for p in all_positions if p.status == "OPEN"]
            
            total_unrealized_pnl = sum(
                (p.current_price - p.entry_price) * p.size * (1 if p.side == "LONG" else -1)
                for p in active_positions
            )
            
            # Get unique strategies and accounts (using strategy_id as account identifier)
            active_strategy_ids = set(p.strategy_id for p in all_positions if p.status == "OPEN" and p.strategy_id)
            active_strategies = len(active_strategy_ids)
            active_accounts = len(active_strategy_ids)  # Same as strategies in this context
            
            return {
                "total_balance": total_balance,
                "total_available": total_available,
                "total_margin_used": 0.0,  # Would need margin calculation
                "total_unrealized_pnl": total_unrealized_pnl,
                "total_realized_pnl": 0.0,  # Would need to calculate from closed positions
                "total_daily_pnl": 0.0,  # Would need to calculate from daily trades
                "total_weekly_pnl": 0.0,  # Would need to calculate from weekly trades
                "total_monthly_pnl": 0.0,  # Would need to calculate from monthly trades
                "active_positions": len(active_positions),
                "active_strategies": active_strategies,
                "active_accounts": active_accounts,
                "total_trades": 0,  # Would need to calculate from trade history
                "total_volume": 0.0,  # Would need to calculate from trade history
                "last_updated": datetime.utcnow().isoformat(),
                "market_summary": {
                    "crypto": {
                        "balance": total_balance,
                        "positions": len(active_positions),
                        "unrealized_pnl": total_unrealized_pnl
                    }
                }
            }
            
        except Exception as e:
            logger.error(f"❌ Error getting total balance: {e}")
            return {}

# Global balance tracker instance
balance_tracker = BalanceTracker()
