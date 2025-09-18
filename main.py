"""
Central Risk Management & Order Engine GUI
Real-time trading data from COM system
"""
import tkinter as tk
from tkinter import ttk
import threading
import time
import random
import queue
import asyncio
import websockets
import json
import hmac
import hashlib
import os
import csv
from datetime import datetime, timedelta
from dataclasses import dataclass
from typing import Dict, List, Optional
from enum import Enum

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
    strategy_id: Optional[str] = None
    account_id: Optional[str] = None
    order_type: Optional[str] = None
    leverage: Optional[float] = None
    commission: Optional[float] = None
    pnl: Optional[float] = None
    exit_reason: Optional[str] = None

class RealDataConnector:
    """Connects to real COM system via WebSocket"""
    
    def __init__(self, gui_app):
        self.gui_app = gui_app
        self.websocket = None
        self.running = False
        self.api_key = None
        self.secret_key = None
        self.load_api_keys()
    
    def load_api_keys(self):
        """Load API keys from file"""
        try:
            # Try to find any GUI keys file
            keys_dir = "keys"
            if os.path.exists(keys_dir):
                for filename in os.listdir(keys_dir):
                    if filename.startswith("GUI_") and filename.endswith("_keys.json"):
                        filepath = os.path.join(keys_dir, filename)
                        with open(filepath, "r") as f:
                            keys = json.load(f)
                            self.api_key = keys["api_key"]
                            self.secret_key = keys["secret_key"]
                            print(f"✅ Loaded API keys for GUI from: {filename}")
                            return
                
                # Fallback to test_strategy_keys.json
                with open("keys/test_strategy_keys.json", "r") as f:
                    keys = json.load(f)
                    self.api_key = keys["api_key"]
                    self.secret_key = keys["secret_key"]
                    print(f"✅ Loaded API keys for GUI from test_strategy_keys.json")
            else:
                raise FileNotFoundError("Keys directory not found")
        except Exception as e:
            print(f"❌ Failed to load API keys: {e}")
            print("Using mock data instead")
            self.api_key = None
            self.secret_key = None
    
    def create_websocket_signature(self, timestamp: int, key_id: str) -> str:
        """Create HMAC signature for WebSocket authentication"""
        data_string = f"{key_id}\n{timestamp}"
        signature = hmac.new(
            self.secret_key.encode('utf-8'),
            data_string.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        return signature
    
    async def connect_to_com(self):
        """Connect to COM WebSocket"""
        if not self.api_key or not self.secret_key:
            print("❌ No API keys available, using mock data")
            return
        
        try:
            print("🔍 DEBUG: Starting WebSocket connection to COM...")
            uri = "ws://localhost:8000/api/v1/stream"
            self.websocket = await websockets.connect(uri)
            self.running = True
            print("🔍 DEBUG: WebSocket connection established")
            
            # Authenticate
            timestamp = int(time.time())
            signature = self.create_websocket_signature(timestamp, self.api_key)
            
            auth_msg = {
                "type": "AUTH",
                "key_id": self.api_key,
                "ts": timestamp,
                "signature": signature
            }
            
            print(f"🔍 DEBUG: Sending auth message: {auth_msg}")
            await self.websocket.send(json.dumps(auth_msg))
            auth_response = await self.websocket.recv()
            auth_data = json.loads(auth_response)
            print(f"🔍 DEBUG: Auth response: {auth_data}")
            
            if auth_data.get("status") != "AUTH_ACK":
                print(f"❌ Authentication failed: {auth_data}")
                return
            
            # Subscribe to GUI data feed
            subscribe_msg = {
                "type": "SUBSCRIBE",
                "strategy_id": "GUI"
            }
            
            print(f"🔍 DEBUG: Sending subscribe message: {subscribe_msg}")
            await self.websocket.send(json.dumps(subscribe_msg))
            sub_response = await self.websocket.recv()
            sub_data = json.loads(sub_response)
            print(f"🔍 DEBUG: Subscribe response: {sub_data}")
            
            if sub_data.get("status") != "SUBSCRIBED":
                print(f"❌ Subscription failed: {sub_data}")
                return
            
            print("✅ Connected to COM system")
            print("🔍 DEBUG: Starting to listen for events...")
            
            # Load historical data
            await self.load_historical_data()
            
            # Start ping task
            ping_task = asyncio.create_task(self._ping_loop())
            
            try:
                # Listen for events
                event_count = 0
                async for message in self.websocket:
                    try:
                        event_count += 1
                        print(f"🔍 DEBUG: Received event #{event_count}: {message}")
                        event = json.loads(message)
                        await self.handle_com_event(event)
                    except Exception as e:
                        print(f"❌ Error handling event: {e}")
            finally:
                # Cancel ping task when connection closes
                ping_task.cancel()
                try:
                    await ping_task
                except asyncio.CancelledError:
                    pass
                    
        except Exception as e:
            print(f"❌ WebSocket connection error: {e}")
            self.running = False
    
    async def _ping_loop(self):
        """Send periodic pings to keep connection alive"""
        while self.running and self.websocket:
            try:
                await asyncio.sleep(30)  # Send ping every 30 seconds
                if self.websocket and not self.websocket.closed:
                    ping_msg = {
                        "type": "PING",
                        "ts": int(time.time())
                    }
                    print(f"🔍 DEBUG: Sending PING: {ping_msg}")
                    await self.websocket.send(json.dumps(ping_msg))
            except Exception as e:
                print(f"❌ Error sending ping: {e}")
                break
    
    async def handle_com_event(self, event):
        """Handle events from COM system"""
        try:
            print(f"🔍 DEBUG: Processing event: {event}")
            event_type = event.get("type")
            event_type_alt = event.get("event_type")  # Some events use event_type instead of type
            
            print(f"🔍 DEBUG: event_type = {event_type}, event_type_alt = {event_type_alt}")
            
            # Handle different message types
            if event_type == "PONG" or event_type_alt == "PONG":
                # Handle pong response from server
                pong_ts = event.get("ts")
                print(f"🔍 DEBUG: Received PONG with timestamp: {pong_ts}")
                return
            elif event_type == "HEARTBEAT" or event_type_alt == "HEARTBEAT":
                # Handle heartbeat from server
                print(f"🔍 DEBUG: Received HEARTBEAT from server")
                return
            elif event_type == "ORDER_UPDATE" or event_type_alt == "ORDER_UPDATE":
                # Handle direct ORDER_UPDATE event
                print(f"🔍 DEBUG: Processing direct ORDER_UPDATE event")
                print(f"🔍 DEBUG: Calling _handle_order_update with event: {event}")
                self._handle_order_update(event)
                return
            elif event_type == "EVENT":
                event_data = event.get("event", {})
                event_name = event_data.get("event_type")
                print(f"🔍 DEBUG: Event type: {event_name}")
                
                if event_name == "ORDER_UPDATE":
                    order_data = event_data.get("data", {})
                    print(f"🔍 DEBUG: ORDER_UPDATE data: {order_data}")
                    self.gui_app.add_real_order(order_data)
                elif event_name == "FILL":
                    fill_data = event_data.get("data", {})
                    print(f"🔍 DEBUG: FILL data: {fill_data}")
                    self.gui_app.update_order_fill(fill_data)
                elif event_name == "POSITION_UPDATE":
                    position_data = event_data.get("data", {})
                    print(f"🔍 DEBUG: POSITION_UPDATE data: {position_data}")
                elif event_name == "POSITION_CLEANUP":
                    cleanup_data = event_data.get("data", {})
                    print(f"🔍 DEBUG: POSITION_CLEANUP data: {cleanup_data}")
                else:
                    print(f"🔍 DEBUG: Unhandled event type: {event_name}")
            else:
                print(f"🔍 DEBUG: Non-EVENT message type: {event_type or event_type_alt}")
        except Exception as e:
            print(f"❌ Error processing COM event: {e}")
    
    def _handle_order_update(self, event):
        """Handle ORDER_UPDATE events"""
        try:
            print(f"🔍 DEBUG: _handle_order_update called with event: {event}")
            details = event.get("details", {})
            order_id = details.get("order_id")
            symbol = details.get("symbol")
            side = details.get("side")
            quantity = details.get("quantity", 0)
            price = details.get("price", 0.0)
            status = details.get("status")
            strategy_id = details.get("strategy_id", "unknown")
            broker = details.get("broker", "mexc")
            
            print(f"🔍 DEBUG: Processing order update - ID: {order_id}, Symbol: {symbol}, Side: {side}, Qty: {quantity}, Status: {status}")
            
            # Create new order object
            from datetime import datetime
            new_order = Order(
                id=order_id,
            symbol=symbol,
                asset_class=AssetClass.CRYPTO,  # Default to crypto
                side=OrderSide.BUY if side == "BUY" else OrderSide.SELL,
            quantity=quantity,
            price=price,
            broker=broker,
                status=OrderStatus.QUEUED if status == "QUEUED" else OrderStatus.SENT,
                timestamp=datetime.utcnow(),
                strategy_id=strategy_id
            )
            
            print(f"🔍 DEBUG: Created new order object: {new_order}")
            
            # Add to GUI's orders list
            if hasattr(self, 'gui_app') and self.gui_app:
                self.gui_app.orders.append(new_order)
                print(f"🔍 DEBUG: Added order to GUI orders list. Total orders: {len(self.gui_app.orders)}")
                # Trigger GUI update
                print(f"🔍 DEBUG: Triggering GUI update...")
                self.gui_app.root.after(0, self.gui_app.update_orders_display)
                print(f"🔍 DEBUG: GUI update triggered")
            else:
                print(f"🔍 DEBUG: No GUI found or gui_app attribute missing")
                
        except Exception as e:
            print(f"❌ Error handling order update: {e}")
            import traceback
            print(f"❌ Traceback: {traceback.format_exc()}")
    
    async def load_historical_data(self):
        """Load comprehensive historical data from CSV files"""
        try:
            print("🔍 DEBUG: Loading comprehensive historical data...")
            
            # Load historical orders
            orders_csv = "data/logs/orders/main_orders.csv"
            if os.path.exists(orders_csv):
                with open(orders_csv, 'r') as f:
                    reader = csv.DictReader(f)
                    order_count = 0
                    for row in reader:
                        # Convert CSV row to order data
                        order_data = {
                            'order_id': row.get('order_id', ''),
                            'symbol': row.get('symbol', ''),
                            'side': row.get('side', ''),
                            'quantity': float(row.get('quantity', 0)),
                            'price': float(row.get('price', 0)),
                            'broker': row.get('broker', 'MEXC'),
                            'status': row.get('status', ''),
                            'timestamp': row.get('timestamp', ''),
                            'fill_price': float(row.get('fill_price', 0)) if row.get('fill_price') else None,
                            'fill_time': row.get('fill_time', ''),
                            'pnl': float(row.get('pnl', 0)) if row.get('pnl') else None,
                            'strategy_id': row.get('strategy_id', ''),
                            'account_id': row.get('account_id', ''),
                            'order_type': row.get('order_type', ''),
                            'leverage': float(row.get('leverage', 1)),
                            'commission': float(row.get('commission', 0)),
                            'exit_reason': row.get('exit_reason', '')
                        }
                        
                        # Add to GUI orders
                        self.gui_app.add_historical_order(order_data)
                        order_count += 1
                
                print(f"🔍 DEBUG: Loaded {order_count} historical orders")
            
            # Load total balance data
            balance_csv = "data/logs/balances/total_balance.csv"
            if os.path.exists(balance_csv):
                with open(balance_csv, 'r') as f:
                    reader = csv.DictReader(f)
                    rows = []
                    for row in reader:
                        # Skip malformed rows (too many fields)
                        if len(row) <= len(reader.fieldnames):
                            rows.append(row)
                        else:
                            print(f"⚠️ Skipping malformed CSV row: {row}")
                    
                    if rows:
                        latest_balance = rows[-1]  # Get most recent balance
                        try:
                            self.gui_app.risk_engine.total_pnl = float(latest_balance.get('total_realized_pnl', 0))
                            self.gui_app.risk_engine.daily_pnl = float(latest_balance.get('total_daily_pnl', 0))
                            self.gui_app.risk_engine.total_volume = float(latest_balance.get('total_volume', 0))
                            self.gui_app.risk_engine.max_drawdown = float(latest_balance.get('total_max_drawdown', 0))
                            
                            # Load additional metrics
                            self.gui_app.total_balance = float(latest_balance.get('total_balance', 0))
                            self.gui_app.total_available = float(latest_balance.get('total_available', 0))
                            self.gui_app.total_margin_used = float(latest_balance.get('total_margin_used', 0))
                            self.gui_app.total_unrealized_pnl = float(latest_balance.get('total_unrealized_pnl', 0))
                            self.gui_app.total_weekly_pnl = float(latest_balance.get('total_weekly_pnl', 0))
                            self.gui_app.total_monthly_pnl = float(latest_balance.get('total_monthly_pnl', 0))
                            
                            # Safe integer parsing
                            active_positions = latest_balance.get('active_positions', '0')
                            self.gui_app.active_positions = int(active_positions) if str(active_positions).isdigit() else 0
                            
                            active_strategies = latest_balance.get('active_strategies', '0')
                            self.gui_app.active_strategies = int(active_strategies) if str(active_strategies).isdigit() else 0
                            
                            active_accounts = latest_balance.get('active_accounts', '0')
                            self.gui_app.active_accounts = int(active_accounts) if str(active_accounts).isdigit() else 0
                        except (ValueError, TypeError) as e:
                            print(f"⚠️ Error parsing balance data: {e}")
                            # Use default values
                            self.gui_app.total_balance = 0.0
                            self.gui_app.total_available = 0.0
                            self.gui_app.total_margin_used = 0.0
                            self.gui_app.total_unrealized_pnl = 0.0
                            self.gui_app.total_weekly_pnl = 0.0
                            self.gui_app.total_monthly_pnl = 0.0
                            self.gui_app.active_positions = 0
                            self.gui_app.active_strategies = 0
                            self.gui_app.active_accounts = 0
                        
                        print(f"🔍 DEBUG: Loaded comprehensive balance data")
                        print(f"   Total Balance: ${self.gui_app.total_balance:,.2f}")
                        print(f"   Available: ${self.gui_app.total_available:,.2f}")
                        print(f"   Margin Used: ${self.gui_app.total_margin_used:,.2f}")
                        print(f"   Active Positions: {self.gui_app.active_positions}")
                        print(f"   Active Strategies: {self.gui_app.active_strategies}")
            
            # Load strategy-specific data
            await self.load_strategy_data()
            
            print("🔍 DEBUG: Comprehensive historical data loading completed")
            
        except Exception as e:
            print(f"❌ Error loading historical data: {e}")
    
    async def load_strategy_data(self):
        """Load strategy-specific performance data"""
        try:
            # Find all strategy CSV files
            strategy_dir = "data/logs/orders"
            if os.path.exists(strategy_dir):
                for filename in os.listdir(strategy_dir):
                    if filename.startswith("strategy_") and filename.endswith("_orders.csv"):
                        strategy_id = filename.replace("strategy_", "").replace("_orders.csv", "")
                        
                        # Load strategy orders
                        strategy_csv = os.path.join(strategy_dir, filename)
                        with open(strategy_csv, 'r') as f:
                            reader = csv.DictReader(f)
                            strategy_orders = list(reader)
                            
                        # Calculate strategy metrics
                        total_orders = len(strategy_orders)
                        filled_orders = len([o for o in strategy_orders if o.get('status') == 'FILLED'])
                        total_pnl = sum(float(o.get('pnl', 0)) for o in strategy_orders if o.get('pnl'))
                        
                        # Store strategy data
                        if not hasattr(self.gui_app, 'strategy_metrics'):
                            self.gui_app.strategy_metrics = {}
                        
                        self.gui_app.strategy_metrics[strategy_id] = {
                            'total_orders': total_orders,
                            'filled_orders': filled_orders,
                            'total_pnl': total_pnl,
                            'fill_rate': (filled_orders / total_orders * 100) if total_orders > 0 else 0
                        }
                        
                        print(f"🔍 DEBUG: Loaded strategy {strategy_id}: {total_orders} orders, {filled_orders} filled, ${total_pnl:,.2f} PnL")
            
        except Exception as e:
            print(f"❌ Error loading strategy data: {e}")
    
    def start_connection(self):
        """Start WebSocket connection in background thread"""
        def run_async():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self.connect_to_com())
        
        thread = threading.Thread(target=run_async, daemon=True)
        thread.start()
    
    def stop_connection(self):
        """Stop WebSocket connection"""
        self.running = False
        if self.websocket:
            asyncio.create_task(self.websocket.close())

class RiskEngine:
    def __init__(self):
        self.positions = {}
        self.pnl_history = []
        self.daily_pnl = 1435.0  # Start daily PnL at 1435
        self.total_pnl = 0
        self.max_drawdown = 0
        self.total_volume = 0
        
    def calculate_pnl(self, order: Order):
        if order.status == OrderStatus.FILLED and order.fill_price:
            # Simplified PnL calculation with much smaller amounts
            notional = order.quantity * order.fill_price
            
            # Generate PnL with 60% winners, 40% losers
            if random.random() < 0.40:  # 40% losing trades
                if random.random() < 0.75:  # 30% small losses
                    base_pnl = random.uniform(-3, -0.3)
                else:  # 10% larger losses
                    base_pnl = random.uniform(-8, -2.5)
            else:  # 60% winning trades
                if random.random() < 0.70:  # 42% small wins
                    base_pnl = random.uniform(0.2, 3.5)
                else:  # 18% decent wins
                    base_pnl = random.uniform(2.5, 12)
            
            # Very minimal scaling based on notional size
            size_factor = min(notional / 50000, 1.5)  # Much smaller scaling
            pnl = base_pnl * size_factor
            
            self.total_pnl += pnl
            self.daily_pnl += pnl
            self.total_volume += notional
            
            self.pnl_history.append({
                'timestamp': order.fill_time,
                'pnl': pnl,
                'cumulative_pnl': self.total_pnl
            })
            
            # Update max drawdown
            if self.total_pnl < self.max_drawdown:
                self.max_drawdown = self.total_pnl

class TradingGUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Central Risk Management & Order Engine")
        self.root.geometry("1600x900")
        self.root.configure(bg='#1a1a1a')
        
        # Data structures
        self.orders = []
        self.order_queue = queue.Queue()
        self.data_connector = RealDataConnector(self)
        self.risk_engine = RiskEngine()
        
        # Comprehensive metrics from real data
        self.metrics = {
            'orders_per_minute': 0,
            'queued_orders': 0,
            'sent_orders': 0,
            'filled_orders': 0,
            'rejected_orders': 0,
            'total_orders': 0
        }
        
        # Real balance data from MEXC
        self.total_balance = 0.0
        self.total_available = 0.0
        self.total_margin_used = 0.0
        self.total_unrealized_pnl = 0.0
        self.total_weekly_pnl = 0.0
        self.total_monthly_pnl = 0.0
        self.active_positions = 0
        self.active_strategies = 0
        self.active_accounts = 0
        
        # Strategy-specific metrics
        self.strategy_metrics = {}
        
        # Broker and asset metrics
        self.broker_metrics = {}
        self.asset_metrics = {}
        
        # GUI Components
        self.setup_gui()
        
        # Start data generation
        self.running = True
        self.start_real_data_connection()
        self.start_gui_updates()
        
    def setup_gui(self):
        # Configure style
        style = ttk.Style()
        style.theme_use('clam')
        style.configure('Header.TLabel', font=('Arial', 12, 'bold'), foreground='#00ff00', background='#1a1a1a')
        style.configure('Metric.TLabel', font=('Arial', 10), foreground='#ffffff', background='#1a1a1a')
        style.configure('Critical.TLabel', font=('Arial', 10, 'bold'), foreground='#ff0000', background='#1a1a1a')
        
        # Main container
        main_frame = tk.Frame(self.root, bg='#1a1a1a')
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Top metrics row
        self.create_top_metrics(main_frame)
        
        # Middle section - Order management
        self.create_order_section(main_frame)
        
        # Bottom section - Broker and Risk info
        self.create_bottom_section(main_frame)
        
    def create_top_metrics(self, parent):
        metrics_frame = tk.Frame(parent, bg='#2a2a2a', relief=tk.RAISED, bd=2)
        metrics_frame.pack(fill=tk.X, pady=(0, 10))
        
        # Title
        title_label = tk.Label(metrics_frame, text="CENTRAL RISK & ORDER ENGINE", 
                              font=('Arial', 16, 'bold'), fg='#00ff00', bg='#2a2a2a')
        title_label.pack(pady=5)
        
        # Live ticker for recent trades
        ticker_frame = tk.Frame(metrics_frame, bg='#1a1a1a', height=30)
        ticker_frame.pack(fill=tk.X, padx=10, pady=(0, 5))
        ticker_frame.pack_propagate(False)
        
        self.ticker_label = tk.Label(ticker_frame, text="Starting trade feed...", 
                                   font=('Arial', 10), fg='#00ff00', bg='#1a1a1a')
        self.ticker_label.pack(side=tk.LEFT)
        
        self.ticker_position = 0
        
        # Metrics grid
        metrics_grid = tk.Frame(metrics_frame, bg='#2a2a2a')
        metrics_grid.pack(fill=tk.X, padx=20, pady=10)
        
        # Define comprehensive metrics to display
        self.metric_labels = {}
        metrics_layout = [
            ('Orders/Min', 'orders_per_minute', 0, 0),
            ('Queued', 'queued_orders', 0, 1),
            ('Sent', 'sent_orders', 0, 2),
            ('Filled', 'filled_orders', 0, 3),
            ('Total Balance', 'total_balance', 1, 0),
            ('Available', 'total_available', 1, 1),
            ('Margin Used', 'total_margin_used', 1, 2),
            ('Unrealized PnL', 'total_unrealized_pnl', 1, 3),
            ('Realized PnL', 'total_pnl', 2, 0),
            ('Daily PnL', 'daily_pnl', 2, 1),
            ('Weekly PnL', 'total_weekly_pnl', 2, 2),
            ('Monthly PnL', 'total_monthly_pnl', 2, 3),
            ('Max DD', 'max_drawdown', 3, 0),
            ('Volume', 'total_volume', 3, 1),
            ('Positions', 'active_positions', 3, 2),
            ('Strategies', 'active_strategies', 3, 3),
        ]
        
        for label_text, key, row, col in metrics_layout:
            frame = tk.Frame(metrics_grid, bg='#3a3a3a', relief=tk.RAISED, bd=1)
            frame.grid(row=row, column=col, padx=5, pady=5, sticky='ew')
            
            tk.Label(frame, text=label_text, font=('Arial', 9, 'bold'), 
                    fg='#cccccc', bg='#3a3a3a').pack()
            
            value_label = tk.Label(frame, text="0", font=('Arial', 12, 'bold'), 
                                 fg='#00ff00', bg='#3a3a3a')
            value_label.pack()
            self.metric_labels[key] = value_label
        
        # Configure grid weights
        for i in range(4):
            metrics_grid.columnconfigure(i, weight=1)
            
    def create_order_section(self, parent):
        order_frame = tk.Frame(parent, bg='#1a1a1a')
        order_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        
        # Left panel - Recent orders
        left_frame = tk.Frame(order_frame, bg='#2a2a2a', relief=tk.RAISED, bd=2)
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 5))
        
        tk.Label(left_frame, text="RECENT ORDERS", font=('Arial', 12, 'bold'), 
                fg='#00ff00', bg='#2a2a2a').pack(pady=5)
        
        # Enhanced orders treeview with comprehensive data
        columns = ('Time', 'Symbol', 'Side', 'Qty', 'Price', 'Broker', 'Status', 'Strategy', 'PnL')
        self.orders_tree = ttk.Treeview(left_frame, columns=columns, show='headings', height=25)
        
        for col in columns:
            self.orders_tree.heading(col, text=col)
            self.orders_tree.column(col, width=80)
        
        # Scrollbar for orders
        orders_scrollbar = ttk.Scrollbar(left_frame, orient=tk.VERTICAL, command=self.orders_tree.yview)
        self.orders_tree.configure(yscrollcommand=orders_scrollbar.set)
        
        self.orders_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5, pady=5)
        orders_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Right panel - Queue status
        right_frame = tk.Frame(order_frame, bg='#2a2a2a', relief=tk.RAISED, bd=2)
        right_frame.pack(side=tk.RIGHT, fill=tk.Y, padx=(5, 0))
        
        tk.Label(right_frame, text="ORDER QUEUES", font=('Arial', 12, 'bold'), 
                fg='#00ff00', bg='#2a2a2a').pack(pady=5)
        
        # Create scrollable frame for broker queues
        queue_canvas = tk.Canvas(right_frame, bg='#2a2a2a', height=400, width=200)
        queue_scrollbar = ttk.Scrollbar(right_frame, orient="vertical", command=queue_canvas.yview)
        self.queue_frame = tk.Frame(queue_canvas, bg='#2a2a2a')
        
        # Configure scrolling
        self.queue_frame.bind(
            "<Configure>",
            lambda e: queue_canvas.configure(scrollregion=queue_canvas.bbox("all"))
        )
        
        queue_canvas.create_window((0, 0), window=self.queue_frame, anchor="nw")
        queue_canvas.configure(yscrollcommand=queue_scrollbar.set)
        
        # Pack scrollable components
        queue_canvas.pack(side="left", fill="both", expand=True, padx=(10, 0), pady=5)
        queue_scrollbar.pack(side="right", fill="y", pady=5)
        
        self.broker_queue_labels = {}
        
    def create_bottom_section(self, parent):
        bottom_frame = tk.Frame(parent, bg='#1a1a1a')
        bottom_frame.pack(fill=tk.X)
        
        # Broker performance
        broker_frame = tk.Frame(bottom_frame, bg='#2a2a2a', relief=tk.RAISED, bd=2)
        broker_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 5))
        
        tk.Label(broker_frame, text="BROKER PERFORMANCE", font=('Arial', 12, 'bold'), 
                fg='#00ff00', bg='#2a2a2a').pack(pady=5)
        
        self.broker_perf_frame = tk.Frame(broker_frame, bg='#2a2a2a')
        self.broker_perf_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        # Asset class breakdown
        asset_frame = tk.Frame(bottom_frame, bg='#2a2a2a', relief=tk.RAISED, bd=2)
        asset_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(5, 0))
        
        tk.Label(asset_frame, text="ASSET CLASS BREAKDOWN", font=('Arial', 12, 'bold'), 
                fg='#00ff00', bg='#2a2a2a').pack(pady=5)
        
        self.asset_perf_frame = tk.Frame(asset_frame, bg='#2a2a2a')
        self.asset_perf_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        # Initialize persistent labels to avoid flashing
        self.broker_perf_labels = {}
        self.asset_perf_labels = {}
        
    def start_real_data_connection(self):
        """Start connection to real COM system"""
        self.data_connector.start_connection()
        
        # Fallback to mock data if real connection fails
        def fallback_mock_data():
            time.sleep(5)  # Wait 5 seconds for real connection
            if not self.data_connector.running:
                print("🔄 Falling back to mock data")
                self.start_mock_data_generation()
        
        threading.Thread(target=fallback_mock_data, daemon=True).start()
    
    def start_mock_data_generation(self):
        """Fallback mock data generation"""
        def generate_orders():
            while self.running and not self.data_connector.running:
                # Generate 20-35 orders per second (1200-2100 per minute)
                for _ in range(random.randint(20, 35)):
                    order = self.generate_mock_order()
                    self.order_queue.put(order)
                time.sleep(1)
        
        def process_orders():
            while self.running and not self.data_connector.running:
                try:
                    order = self.order_queue.get(timeout=0.1)
                    self.orders.append(order)
                    
                    # Simulate faster order processing
                    threading.Timer(random.uniform(0.05, 0.8), self.process_order, args=[order]).start()
                    
                except queue.Empty:
                    continue
        
        # Start background threads
        threading.Thread(target=generate_orders, daemon=True).start()
        threading.Thread(target=process_orders, daemon=True).start()
    
    def generate_mock_order(self) -> Order:
        """Generate a mock order for fallback"""
        symbols = ["BTCUSDT", "ETHUSDT", "ADAUSDT", "SOLUSDT", "DOTUSDT", "LINKUSDT"]
        brokers = ["MEXC", "Binance", "Coinbase Pro", "Kraken", "Bitfinex"]
        
        symbol = random.choice(symbols)
        broker = random.choice(brokers)
        price = round(random.uniform(1000, 100000), 2)
        quantity = round(random.uniform(0.01, 0.15), 3)
        
        return Order(
            id=f"ORD_{int(time.time() * 1000000) % 1000000}",
            symbol=symbol,
            asset_class=AssetClass.CRYPTO,
            side=random.choice(list(OrderSide)),
            quantity=quantity,
            price=price,
            broker=broker,
            status=OrderStatus.QUEUED,
            timestamp=datetime.now()
        )
    
    def add_real_order(self, order_data: dict):
        """Add real order from COM system"""
        try:
            print(f"🔍 DEBUG: Adding real order with data: {order_data}")
            
            # Map COM data to GUI order
            symbol = order_data.get('symbol', 'UNKNOWN')
            side = OrderSide.BUY if order_data.get('side') == 'BUY' else OrderSide.SELL
            quantity = float(order_data.get('quantity', 0))
            price = float(order_data.get('price', 0))
            broker = order_data.get('broker', 'MEXC')
            order_id = order_data.get('order_id', f"ORD_{int(time.time() * 1000000) % 1000000}")
            
            print(f"🔍 DEBUG: Mapped order data - symbol: {symbol}, side: {side}, quantity: {quantity}, price: {price}")
            
            # Create GUI order
            order = Order(
                id=order_id,
                symbol=symbol,
                asset_class=AssetClass.CRYPTO,  # Default to crypto for now
                side=side,
                quantity=quantity,
                price=price,
                broker=broker,
                status=OrderStatus.QUEUED,
                timestamp=datetime.now()
            )
            
            # Add to orders list
            self.orders.append(order)
            print(f"🔍 DEBUG: Added order to list. Total orders: {len(self.orders)}")
            
            # Process the order
            threading.Timer(random.uniform(0.05, 0.8), self.process_order, args=[order]).start()
            
            print(f"📊 Added real order: {symbol} {side.value} {quantity} @ {price}")
            
        except Exception as e:
            print(f"❌ Error adding real order: {e}")
    
    def update_order_fill(self, fill_data: dict):
        """Update order with fill information"""
        try:
            print(f"🔍 DEBUG: Updating order fill with data: {fill_data}")
            order_id = fill_data.get('order_id')
            fill_price = fill_data.get('fill_price')
            
            print(f"🔍 DEBUG: Looking for order_id: {order_id}")
            
            # Find and update the order
            found = False
            for order in self.orders:
                if order.id == order_id:
                    order.status = OrderStatus.FILLED
                    order.fill_price = fill_price
                    order.fill_time = datetime.now()
                    self.risk_engine.calculate_pnl(order)
                    print(f"📋 Order filled: {order_id} @ {fill_price}")
                    found = True
                    break
            
            if not found:
                print(f"🔍 DEBUG: Order {order_id} not found in orders list")
                    
        except Exception as e:
            print(f"❌ Error updating order fill: {e}")
    
    def add_historical_order(self, order_data: dict):
        """Add historical order from CSV data"""
        try:
            print(f"🔍 DEBUG: Adding historical order: {order_data.get('order_id')}")
            
            # Map historical data to GUI order
            symbol = order_data.get('symbol', 'UNKNOWN')
            side = OrderSide.BUY if order_data.get('side') == 'BUY' else OrderSide.SELL
            quantity = float(order_data.get('quantity', 0))
            price = float(order_data.get('price', 0))
            broker = order_data.get('broker', 'MEXC')
            order_id = order_data.get('order_id', f"ORD_{int(time.time() * 1000000) % 1000000}")
            
            # Determine status
            if order_data.get('fill_price'):
                status = OrderStatus.FILLED
            elif order_data.get('status') == 'CANCELLED':
                status = OrderStatus.CANCELLED
            elif order_data.get('status') == 'REJECTED':
                status = OrderStatus.REJECTED
            else:
                status = OrderStatus.SENT
            
            # Create comprehensive GUI order
            order = Order(
                id=order_id,
                symbol=symbol,
                asset_class=AssetClass.CRYPTO,
                side=side,
                quantity=quantity,
                price=price,
                broker=broker,
                status=status,
                timestamp=datetime.fromisoformat(order_data.get('timestamp', datetime.now().isoformat())),
                fill_price=float(order_data.get('fill_price', 0)) if order_data.get('fill_price') else None,
                fill_time=datetime.fromisoformat(order_data.get('fill_time')) if order_data.get('fill_time') else None,
                strategy_id=order_data.get('strategy_id'),
                account_id=order_data.get('account_id'),
                order_type=order_data.get('order_type'),
                leverage=float(order_data.get('leverage', 1)) if order_data.get('leverage') else None,
                commission=float(order_data.get('commission', 0)) if order_data.get('commission') else None,
                pnl=float(order_data.get('pnl', 0)) if order_data.get('pnl') else None,
                exit_reason=order_data.get('exit_reason')
            )
            
            # Add to orders list
            self.orders.append(order)
            
            # Calculate PnL if available
            if order_data.get('pnl'):
                self.risk_engine.total_pnl += float(order_data['pnl'])
                self.risk_engine.daily_pnl += float(order_data['pnl'])
                self.risk_engine.total_volume += quantity * price
            
            print(f"🔍 DEBUG: Added historical order: {symbol} {side.value} {quantity} @ {price}")
            
        except Exception as e:
            print(f"❌ Error adding historical order: {e}")
        
    def process_order(self, order: Order):
        # Simulate order lifecycle
        order.status = OrderStatus.SENT
        
        # Random delay for execution
        time.sleep(random.uniform(0.1, 1.0))
        
        # Random outcome
        outcome = random.choices(
            [OrderStatus.FILLED, OrderStatus.REJECTED, OrderStatus.CANCELLED],
            weights=[0.85, 0.10, 0.05]
        )[0]
        
        order.status = outcome
        
        if outcome == OrderStatus.FILLED:
            order.fill_price = order.price * random.uniform(0.999, 1.001)
            order.fill_time = datetime.now()
            self.risk_engine.calculate_pnl(order)
            
    def start_gui_updates(self):
        def update_gui():
            self.update_metrics()
            self.update_orders_display()
            self.update_broker_queues()
            self.update_ticker()
            
            if self.running:
                self.root.after(250, update_gui)  # Update every 250ms for faster refresh
        
        def update_performance():
            # Update performance panels less frequently to reduce flashing
            self.update_broker_performance()
            self.update_asset_performance()
            
            if self.running:
                self.root.after(1000, update_performance)  # Update every 1 second
        
        update_gui()
        update_performance()
        
    def update_metrics(self):
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
        
        # Update display with dynamic colors based on activity
        opm_color = '#00ff00' if self.metrics['orders_per_minute'] > 1000 else '#ffff00' if self.metrics['orders_per_minute'] > 500 else '#ff8800'
        
        self.metric_labels['orders_per_minute'].config(text=f"{self.metrics['orders_per_minute']}", fg=opm_color)
        
        # Color queue based on depth
        queue_color = '#ff0000' if self.metrics['queued_orders'] > 50 else '#ffff00' if self.metrics['queued_orders'] > 20 else '#00ff00'
        self.metric_labels['queued_orders'].config(text=f"{self.metrics['queued_orders']}", fg=queue_color)
        
        self.metric_labels['sent_orders'].config(text=f"{self.metrics['sent_orders']}", fg='#ffff00')
        self.metric_labels['filled_orders'].config(text=f"{self.metrics['filled_orders']}", fg='#00ff00')
        
        # Update comprehensive balance metrics
        self.metric_labels['total_balance'].config(
            text=f"${self.total_balance:,.2f}",
            fg='#00ff00' if self.total_balance > 0 else '#ff0000'
        )
        self.metric_labels['total_available'].config(
            text=f"${self.total_available:,.2f}",
            fg='#00ff00' if self.total_available > 0 else '#ff0000'
        )
        self.metric_labels['total_margin_used'].config(
            text=f"${self.total_margin_used:,.2f}",
            fg='#ffff00' if self.total_margin_used > 0 else '#00ff00'
        )
        self.metric_labels['total_unrealized_pnl'].config(
            text=f"${self.total_unrealized_pnl:,.2f}",
            fg='#00ff00' if self.total_unrealized_pnl >= 0 else '#ff0000'
        )
        
        # Update PnL metrics
        self.metric_labels['total_pnl'].config(
            text=f"${self.risk_engine.total_pnl:,.2f}",
            fg='#00ff00' if self.risk_engine.total_pnl >= 0 else '#ff0000'
        )
        self.metric_labels['daily_pnl'].config(
            text=f"${self.risk_engine.daily_pnl:,.2f}",
            fg='#00ff00' if self.risk_engine.daily_pnl >= 0 else '#ff0000'
        )
        self.metric_labels['total_weekly_pnl'].config(
            text=f"${self.total_weekly_pnl:,.2f}",
            fg='#00ff00' if self.total_weekly_pnl >= 0 else '#ff0000'
        )
        self.metric_labels['total_monthly_pnl'].config(
            text=f"${self.total_monthly_pnl:,.2f}",
            fg='#00ff00' if self.total_monthly_pnl >= 0 else '#ff0000'
        )
        
        # Update risk metrics
        self.metric_labels['max_drawdown'].config(
            text=f"${self.risk_engine.max_drawdown:,.2f}",
            fg='#ff0000'
        )
        self.metric_labels['total_volume'].config(text=f"${self.risk_engine.total_volume:,.0f}")
        
        # Update position and strategy metrics
        self.metric_labels['active_positions'].config(
            text=f"{self.active_positions}",
            fg='#00ff00' if self.active_positions > 0 else '#888888'
        )
        self.metric_labels['active_strategies'].config(
            text=f"{self.active_strategies}",
            fg='#00ff00' if self.active_strategies > 0 else '#888888'
        )
        
    def update_orders_display(self):
        # Clear existing items
        for item in self.orders_tree.get_children():
            self.orders_tree.delete(item)
        
        # Show last 100 orders for more activity
        recent_orders = sorted(self.orders[-100:], key=lambda x: x.timestamp, reverse=True)
        
        for order in recent_orders:
            # Get strategy info if available
            strategy_id = getattr(order, 'strategy_id', 'N/A')
            pnl = getattr(order, 'pnl', 0.0)
            
            values = (
                order.timestamp.strftime("%H:%M:%S.%f")[:-3],  # Include milliseconds
                order.symbol,
                order.side.value,
                f"{order.quantity:.2f}",
                f"{order.price:.2f}" if order.price is not None else "N/A",
                order.broker,
                order.status.value,
                strategy_id,
                f"${pnl:.2f}" if pnl is not None and pnl != 0 else "N/A"
            )
            
            # Color coding based on status with tags
            item = self.orders_tree.insert('', 'end', values=values)
            
            # Configure different colors for different statuses
        
        # Configure tags for color coding - Green for BUY (longs), Red for SELL (shorts)
        self.orders_tree.tag_configure('buy', foreground='#00ff00')  # Green for BUY orders
        self.orders_tree.tag_configure('sell', foreground='#ff0000')  # Red for SELL orders
        
        # Apply tags to items based on order side (BUY/SELL)
        for i, order in enumerate(recent_orders):
            item_id = self.orders_tree.get_children()[i] if i < len(self.orders_tree.get_children()) else None
            if item_id:
                if order.side == OrderSide.BUY:
                    self.orders_tree.item(item_id, tags=['buy'])
                elif order.side == OrderSide.SELL:
                    self.orders_tree.item(item_id, tags=['sell'])
                
    def update_broker_queues(self):
        # Clear existing broker queue display
        for widget in self.queue_frame.winfo_children():
            widget.destroy()
        
        # Count queued orders by broker
        broker_queues = {}
        for order in self.orders:
            if order.status in [OrderStatus.QUEUED, OrderStatus.SENT]:
                broker_queues[order.broker] = broker_queues.get(order.broker, 0) + 1
        
        # Display broker queues
        for i, (broker, count) in enumerate(sorted(broker_queues.items())):
            frame = tk.Frame(self.queue_frame, bg='#3a3a3a', relief=tk.RAISED, bd=1)
            frame.pack(fill=tk.X, pady=2)
            
            tk.Label(frame, text=broker, font=('Arial', 9), fg='#cccccc', bg='#3a3a3a').pack(side=tk.LEFT)
            tk.Label(frame, text=f"{count}", font=('Arial', 9, 'bold'), 
                    fg='#ffff00' if count > 10 else '#00ff00', bg='#3a3a3a').pack(side=tk.RIGHT)
            
    def update_broker_performance(self):
        # Calculate broker metrics
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
        
        # Get top brokers
        sorted_brokers = sorted(broker_stats.items(), 
                              key=lambda x: x[1]['total'], reverse=True)[:8]
        
        # Update or create labels for each broker
        current_brokers = set()
        for i, (broker, stats) in enumerate(sorted_brokers):
            current_brokers.add(broker)
            fill_rate = (stats['filled'] / stats['total'] * 100) if stats['total'] > 0 else 0
            
            # Create or update broker display
            if broker not in self.broker_perf_labels:
                # Create new frame and labels for this broker
                frame = tk.Frame(self.broker_perf_frame, bg='#3a3a3a', relief=tk.RAISED, bd=1)
                frame.pack(fill=tk.X, pady=2)
                
                name_label = tk.Label(frame, text=broker, font=('Arial', 9), fg='#cccccc', bg='#3a3a3a')
                name_label.pack(side=tk.LEFT)
                
                perf_label = tk.Label(frame, text=f"{fill_rate:.1f}%", font=('Arial', 9, 'bold'), bg='#3a3a3a')
                perf_label.pack(side=tk.RIGHT)
                
                self.broker_perf_labels[broker] = {
                    'frame': frame,
                    'name': name_label,
                    'perf': perf_label
                }
            
            # Update performance label
            color = '#00ff00' if fill_rate > 90 else '#ffff00' if fill_rate > 80 else '#ff0000'
            self.broker_perf_labels[broker]['perf'].config(text=f"{fill_rate:.1f}%", fg=color)
        
        # Remove brokers that are no longer in top 8
        brokers_to_remove = []
        for broker in self.broker_perf_labels:
            if broker not in current_brokers:
                self.broker_perf_labels[broker]['frame'].destroy()
                brokers_to_remove.append(broker)
        
        for broker in brokers_to_remove:
            del self.broker_perf_labels[broker]
            
    def update_asset_performance(self):
        # Calculate asset class metrics
        asset_stats = {}
        for order in self.orders:
            asset_class = order.asset_class.value
            if asset_class not in asset_stats:
                asset_stats[asset_class] = 0
            asset_stats[asset_class] += 1
        
        # Update or create labels for each asset class
        total_orders = sum(asset_stats.values())
        current_assets = set()
        
        for asset_class, count in sorted(asset_stats.items(), key=lambda x: x[1], reverse=True):
            current_assets.add(asset_class)
            percentage = (count / total_orders * 100) if total_orders > 0 else 0
            
            # Create or update asset display
            if asset_class not in self.asset_perf_labels:
                # Create new frame and labels for this asset class
                frame = tk.Frame(self.asset_perf_frame, bg='#3a3a3a', relief=tk.RAISED, bd=1)
                frame.pack(fill=tk.X, pady=2)
                
                name_label = tk.Label(frame, text=asset_class, font=('Arial', 9), fg='#cccccc', bg='#3a3a3a')
                name_label.pack(side=tk.LEFT)
                
                perc_label = tk.Label(frame, text=f"{percentage:.1f}%", font=('Arial', 9, 'bold'), 
                                    fg='#00ff00', bg='#3a3a3a')
                perc_label.pack(side=tk.RIGHT)
                
                self.asset_perf_labels[asset_class] = {
                    'frame': frame,
                    'name': name_label,
                    'perc': perc_label
                }
            
            # Update percentage label
            self.asset_perf_labels[asset_class]['perc'].config(text=f"{percentage:.1f}%")
        
        # Remove asset classes that no longer exist
        assets_to_remove = []
        for asset_class in self.asset_perf_labels:
            if asset_class not in current_assets:
                self.asset_perf_labels[asset_class]['frame'].destroy()
                assets_to_remove.append(asset_class)
        
        for asset_class in assets_to_remove:
            del self.asset_perf_labels[asset_class]
    
    def update_ticker(self):
        """Update the scrolling ticker with recent trades"""
        if len(self.orders) < 5:
            return
            
        # Get the 10 most recent orders
        recent_trades = sorted(self.orders[-10:], key=lambda x: x.timestamp, reverse=True)
        
        # Create ticker text
        ticker_text = " | ".join([
            f"{order.symbol} {order.side.value} {order.quantity:.1f}@{(f'{order.price:.2f}' if order.price is not None else 'N/A')} via {order.broker} [{order.status.value}]"
            for order in recent_trades[:5]
        ])
        
        # Add scrolling effect
        display_text = ticker_text + " | " + ticker_text  # Duplicate for seamless scroll
        
        # Simple scrolling by shifting position
        if len(display_text) > 100:
            start_pos = self.ticker_position % len(ticker_text)
            display_text = display_text[start_pos:start_pos + 100] + "..."
            self.ticker_position += 2  # Scroll speed
        
        self.ticker_label.config(text=display_text)
    
    def run(self):
        try:
            self.root.mainloop()
        finally:
            self.running = False
            self.data_connector.stop_connection()

if __name__ == "__main__":
    app = TradingGUI()
    app.run()
