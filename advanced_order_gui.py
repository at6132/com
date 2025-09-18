import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext, filedialog
import json
import requests
from datetime import datetime
from typing import Dict, Any, Optional
import threading
import time
import hmac
import hashlib
import os

class AdvancedOrderFormGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("ATQ Ventures COM - Advanced Order Form")
        self.root.geometry("1000x1000")
        
        # Configuration
        self.com_base_url = "http://localhost:8000"  # COM server URL
        self.api_key = "your_api_key_here"  # Will be loaded from config
        self.secret_key = "your_secret_key_here"  # Will be loaded from config
        
        # Paper trade mode
        self.paper_trade = tk.BooleanVar(value=True)
        
        # Create notebook for tabs
        self.notebook = ttk.Notebook(root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Create tabs
        self.create_order_tab()
        self.create_history_tab()
        self.create_config_tab()
        
        # Initialize form
        self.clear_form()
        
        # Try to load keys automatically
        self.auto_load_keys()
        
    def auto_load_keys(self):
        """Automatically try to load keys from the keys directory"""
        keys_dir = "keys"
        if os.path.exists(keys_dir):
            # Look for any key file
            for filename in os.listdir(keys_dir):
                if filename.endswith('.json') or filename.endswith('KEYS'):
                    filepath = os.path.join(keys_dir, filename)
                    try:
                        with open(filepath, 'r') as f:
                            key_data = json.load(f)
                        
                        self.api_key = key_data.get('api_key', self.api_key)
                        self.secret_key = key_data.get('secret_key', self.secret_key)
                        
                        # Update GUI if it exists
                        if hasattr(self, 'api_key_var'):
                            self.api_key_var.set(self.api_key)
                        if hasattr(self, 'secret_key_var'):
                            self.secret_key_var.set(self.secret_key)
                        
                        print(f"✅ Auto-loaded keys from: {filename}")
                        break
                        
                    except Exception as e:
                        print(f"⚠️  Could not load keys from {filename}: {e}")
        
    def create_order_tab(self):
        """Create the main order form tab"""
        order_frame = ttk.Frame(self.notebook)
        self.notebook.add(order_frame, text="Order Form")
        
        # Create main frame
        main_frame = ttk.Frame(order_frame, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Configure grid weights
        order_frame.columnconfigure(0, weight=1)
        order_frame.rowconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1)
        
        # Title
        title_label = ttk.Label(main_frame, text="ATQ Ventures Central Order Manager", 
                               font=("Arial", 16, "bold"))
        title_label.grid(row=0, column=0, columnspan=2, pady=(0, 20))
        
        # Paper trade checkbox
        paper_frame = ttk.Frame(main_frame)
        paper_frame.grid(row=1, column=0, columnspan=2, pady=(0, 20))
        paper_check = ttk.Checkbutton(paper_frame, text="Paper Trade Mode", 
                                     variable=self.paper_trade)
        paper_check.pack()
        
        # Connection status
        self.status_label = ttk.Label(paper_frame, text="🔴 Disconnected", foreground="red")
        self.status_label.pack(side=tk.RIGHT, padx=10)
        
        # Broker selection
        ttk.Label(main_frame, text="Broker:").grid(row=2, column=0, sticky=tk.W, pady=5)
        self.broker_var = tk.StringVar(value="MEXC")
        broker_combo = ttk.Combobox(main_frame, textvariable=self.broker_var, 
                                   values=["MEXC"], state="readonly")
        broker_combo.grid(row=2, column=1, sticky=(tk.W, tk.E), pady=5)
        
        # Strategy ID
        ttk.Label(main_frame, text="Strategy ID:").grid(row=3, column=0, sticky=tk.W, pady=5)
        self.strategy_id_var = tk.StringVar(value="test_strategy_001")
        strategy_entry = ttk.Entry(main_frame, textvariable=self.strategy_id_var)
        strategy_entry.grid(row=3, column=1, sticky=(tk.W, tk.E), pady=5)
        
        # Symbol
        ttk.Label(main_frame, text="Symbol:").grid(row=4, column=0, sticky=tk.W, pady=5)
        self.symbol_var = tk.StringVar(value="BTCUSDT")
        symbol_entry = ttk.Entry(main_frame, textvariable=self.symbol_var)
        symbol_entry.grid(row=4, column=1, sticky=(tk.W, tk.E), pady=5)
        
        # Side
        ttk.Label(main_frame, text="Side:").grid(row=5, column=0, sticky=tk.W, pady=5)
        self.side_var = tk.StringVar(value="BUY")
        side_combo = ttk.Combobox(main_frame, textvariable=self.side_var, 
                                 values=["BUY", "SELL"], state="readonly")
        side_combo.grid(row=5, column=1, sticky=(tk.W, tk.E), pady=5)
        
        # Order Type
        ttk.Label(main_frame, text="Order Type:").grid(row=6, column=0, sticky=tk.W, pady=5)
        self.order_type_var = tk.StringVar(value="LIMIT")
        order_type_combo = ttk.Combobox(main_frame, textvariable=self.order_type_var, 
                                       values=["MARKET", "LIMIT", "STOP_MARKET", "STOP_LIMIT"], 
                                       state="readonly")
        order_type_combo.grid(row=6, column=1, sticky=(tk.W, tk.E), pady=5)
        
        # Quantity
        ttk.Label(main_frame, text="Quantity:").grid(row=7, column=0, sticky=tk.W, pady=5)
        self.quantity_var = tk.StringVar(value="0.0001")
        quantity_entry = ttk.Entry(main_frame, textvariable=self.quantity_var)
        quantity_entry.grid(row=7, column=1, sticky=(tk.W, tk.E), pady=5)
        
        # Leverage
        ttk.Label(main_frame, text="Leverage:").grid(row=8, column=0, sticky=tk.W, pady=5)
        self.leverage_var = tk.StringVar(value="1")
        leverage_entry = ttk.Entry(main_frame, textvariable=self.leverage_var)
        leverage_entry.grid(row=8, column=1, sticky=(tk.W, tk.E), pady=5)
        
        # Price (for LIMIT orders)
        ttk.Label(main_frame, text="Price:").grid(row=9, column=0, sticky=tk.W, pady=5)
        self.price_var = tk.StringVar(value="50000")
        self.price_entry = ttk.Entry(main_frame, textvariable=self.price_var)
        self.price_entry.grid(row=9, column=1, sticky=(tk.W, tk.E), pady=5)
        
        # Stop Price (for STOP orders)
        ttk.Label(main_frame, text="Stop Price:").grid(row=10, column=0, sticky=tk.W, pady=5)
        self.stop_price_var = tk.StringVar(value="")
        self.stop_price_entry = ttk.Entry(main_frame, textvariable=self.stop_price_var)
        self.stop_price_entry.grid(row=10, column=1, sticky=(tk.W, tk.E), pady=5)
        
        # Time in Force
        ttk.Label(main_frame, text="Time in Force:").grid(row=10, column=0, sticky=tk.W, pady=5)
        self.tif_var = tk.StringVar(value="GTC")
        tif_combo = ttk.Combobox(main_frame, textvariable=self.tif_var, 
                                values=["GTC", "IOC", "FOK"], state="readonly")
        tif_combo.grid(row=10, column=1, sticky=(tk.W, tk.E), pady=5)
        
        # Reduce Only
        ttk.Label(main_frame, text="Reduce Only:").grid(row=11, column=0, sticky=tk.W, pady=5)
        self.reduce_only_var = tk.BooleanVar(value=False)
        reduce_only_check = ttk.Checkbutton(main_frame, text="", 
                                          variable=self.reduce_only_var)
        reduce_only_check.grid(row=11, column=1, sticky=tk.W, pady=5)
        
        # Post Only
        ttk.Label(main_frame, text="Post Only:").grid(row=12, column=0, sticky=tk.W, pady=5)
        self.post_only_var = tk.BooleanVar(value=True)
        post_only_check = ttk.Checkbutton(main_frame, text="", 
                                        variable=self.post_only_var)
        post_only_check.grid(row=12, column=1, sticky=tk.W, pady=5)
        
        # Client Order ID
        ttk.Label(main_frame, text="Client Order ID:").grid(row=13, column=0, sticky=tk.W, pady=5)
        self.client_order_id_var = tk.StringVar(value="")
        client_order_id_entry = ttk.Entry(main_frame, textvariable=self.client_order_id_var)
        client_order_id_entry.grid(row=13, column=1, sticky=(tk.W, tk.E), pady=5)
        
        # Idempotency Key
        ttk.Label(main_frame, text="Idempotency Key:").grid(row=14, column=0, sticky=tk.W, pady=5)
        self.idempotency_key_var = tk.StringVar(value="")
        idempotency_key_entry = ttk.Entry(main_frame, textvariable=self.idempotency_key_var)
        idempotency_key_entry.grid(row=14, column=1, sticky=(tk.W, tk.E), pady=5)
        
        # Notes
        ttk.Label(main_frame, text="Notes:").grid(row=15, column=0, sticky=tk.W, pady=5)
        self.notes_var = tk.StringVar(value="")
        notes_entry = ttk.Entry(main_frame, textvariable=self.notes_var)
        notes_entry.grid(row=15, column=1, sticky=(tk.W, tk.E), pady=5)
        
        # Buttons
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=16, column=0, columnspan=2, pady=20)
        
        send_button = ttk.Button(button_frame, text="Send Order", command=self.send_order)
        send_button.pack(side=tk.LEFT, padx=5)
        
        clear_button = ttk.Button(button_frame, text="Clear Form", command=self.clear_form)
        clear_button.pack(side=tk.LEFT, padx=5)
        
        test_connection_button = ttk.Button(button_frame, text="Test Connection", 
                                          command=self.test_connection)
        test_connection_button.pack(side=tk.LEFT, padx=5)
        
        # Response area
        ttk.Label(main_frame, text="Response:").grid(row=17, column=0, sticky=tk.W, pady=(20, 5))
        self.response_text = scrolledtext.ScrolledText(main_frame, height=15, width=80)
        self.response_text.grid(row=18, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5)
        
        # Configure response text grid weight
        main_frame.rowconfigure(18, weight=1)
        
        # Bind order type change to update UI
        order_type_combo.bind('<<ComboboxSelected>>', self.on_order_type_change)
        
    def create_history_tab(self):
        """Create the order history tab"""
        history_frame = ttk.Frame(self.notebook)
        self.notebook.add(history_frame, text="Order History")
        
        # Title
        title_label = ttk.Label(history_frame, text="Order History", 
                               font=("Arial", 14, "bold"))
        title_label.pack(pady=10)
        
        # Refresh button
        refresh_button = ttk.Button(history_frame, text="Refresh History", 
                                   command=self.refresh_order_history)
        refresh_button.pack(pady=5)
        
        # History treeview
        columns = ("Order ID", "Symbol", "Side", "Type", "Quantity", "Price", "Status", "Created")
        self.history_tree = ttk.Treeview(history_frame, columns=columns, show="headings", height=20)
        
        # Configure columns
        for col in columns:
            self.history_tree.heading(col, text=col)
            self.history_tree.column(col, width=120)
        
        # Add scrollbar
        history_scrollbar = ttk.Scrollbar(history_frame, orient=tk.VERTICAL, command=self.history_tree.yview)
        self.history_tree.configure(yscrollcommand=history_scrollbar.set)
        
        # Pack treeview and scrollbar
        self.history_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10, pady=10)
        history_scrollbar.pack(side=tk.RIGHT, fill=tk.Y, pady=10)
        
    def create_config_tab(self):
        """Create the configuration tab"""
        config_frame = ttk.Frame(self.notebook)
        self.notebook.add(config_frame, text="Configuration")
        
        # Title
        title_label = ttk.Label(config_frame, text="COM Server Configuration", 
                               font=("Arial", 14, "bold"))
        title_label.pack(pady=10)
        
        # Configuration form
        config_form = ttk.Frame(config_frame, padding="20")
        config_form.pack(fill=tk.BOTH, expand=True)
        
        # COM Server URL
        ttk.Label(config_form, text="COM Server URL:").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.server_url_var = tk.StringVar(value=self.com_base_url)
        server_url_entry = ttk.Entry(config_form, textvariable=self.server_url_var, width=50)
        server_url_entry.grid(row=0, column=1, sticky=(tk.W, tk.E), pady=5, padx=(10, 0))
        
        # API Key
        ttk.Label(config_form, text="API Key:").grid(row=1, column=0, sticky=tk.W, pady=5)
        self.api_key_var = tk.StringVar(value=self.api_key)
        api_key_entry = ttk.Entry(config_form, textvariable=self.api_key_var, width=50, show="*")
        api_key_entry.grid(row=1, column=1, sticky=(tk.W, tk.E), pady=5, padx=(10, 0))
        
        # Secret Key
        ttk.Label(config_form, text="Secret Key:").grid(row=2, column=0, sticky=tk.W, pady=5)
        self.secret_key_var = tk.StringVar(value=self.secret_key)
        secret_key_entry = ttk.Entry(config_form, textvariable=self.secret_key_var, width=50, show="*")
        secret_key_entry.grid(row=2, column=1, sticky=(tk.W, tk.E), pady=5, padx=(10, 0))

        # Load keys button
        load_keys_button = ttk.Button(config_form, text="Load Keys from File", 
                                     command=self.load_keys_from_file)
        load_keys_button.grid(row=3, column=0, columnspan=2, pady=10)
        
        # Check keys button
        check_keys_button = ttk.Button(config_form, text="Check Key Status", 
                                     command=self.check_key_status)
        check_keys_button.grid(row=4, column=0, columnspan=2, pady=5)
        
        # Save button
        save_button = ttk.Button(config_form, text="Save Configuration", 
                                command=self.save_configuration)
        save_button.grid(row=5, column=0, columnspan=2, pady=10)
        
        # Test connection button
        test_button = ttk.Button(config_form, text="Test Connection", 
                                command=self.test_connection)
        test_button.grid(row=6, column=0, columnspan=2, pady=5)
        
        # Configure grid weights
        config_form.columnconfigure(1, weight=1)
        
    def load_keys_from_file(self):
        """Load API keys from a JSON file"""
        filepath = filedialog.askopenfilename(
            title="Select Keys File",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
            initialdir="keys" if os.path.exists("keys") else "."
        )
        
        if filepath:
            try:
                with open(filepath, 'r') as f:
                    key_data = json.load(f)
                
                # Update variables
                self.api_key = key_data.get('api_key', self.api_key)
                self.secret_key = key_data.get('secret_key', self.secret_key)
                
                # Update GUI
                self.api_key_var.set(self.api_key)
                self.secret_key_var.set(self.secret_key)
                
                messagebox.showinfo("Success", f"Loaded keys from {os.path.basename(filepath)}")
                
            except Exception as e:
                messagebox.showerror("Error", f"Failed to load keys: {str(e)}")
    
    def on_order_type_change(self, event=None):
        """Update UI based on order type selection"""
        order_type = self.order_type_var.get()
        
        if order_type in ["STOP_MARKET", "STOP_LIMIT"]:
            # Enable stop price field
            self.stop_price_entry.config(state='normal')
        else:
            # Disable stop price field
            self.stop_price_entry.config(state='disabled')
            
        if order_type == "MARKET":
            # Disable price field for market orders
            self.price_entry.config(state='disabled')
        else:
            # Enable price field for other order types
            self.price_entry.config(state='normal')
    
    def generate_idempotency_key(self):
        """Generate a unique idempotency key"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        strategy = self.strategy_id_var.get()
        symbol = self.symbol_var.get()
        return f"{strategy}_{symbol}_{timestamp}"
    
    def clear_form(self):
        """Clear all form fields"""
        self.strategy_id_var.set("test_strategy_001")
        self.symbol_var.set("BTCUSDT")
        self.side_var.set("BUY")
        self.order_type_var.set("LIMIT")
        self.quantity_var.set("0.0001")
        self.leverage_var.set("1")
        self.price_var.set("50000")
        self.stop_price_var.set("")
        self.tif_var.set("GTC")
        self.reduce_only_var.set(False)
        self.post_only_var.set(True)
        self.client_order_id_var.set("")
        self.idempotency_key_var.set(self.generate_idempotency_key())
        self.notes_var.set("")
        self.response_text.delete(1.0, tk.END)
        
        # Update UI based on order type
        self.on_order_type_change()
    
    def validate_form(self) -> bool:
        """Validate form inputs"""
        try:
            quantity = float(self.quantity_var.get())
            if quantity <= 0:
                messagebox.showerror("Validation Error", "Quantity must be greater than 0")
                return False
                
            # Check minimum notional for BTCUSDT (11.1916 USDT)
            if self.symbol_var.get().strip() == "BTCUSDT":
                price = float(self.price_var.get()) if self.order_type_var.get() != "MARKET" else 50000  # Use current price for market orders
                notional = quantity * price
                if notional < 11.1916:
                    messagebox.showerror("Validation Error", f"Minimum notional for BTCUSDT is 11.1916 USDT. Current: {notional:.2f} USDT")
                    return False
                
            leverage = float(self.leverage_var.get())
            if leverage <= 0 or leverage > 500:
                messagebox.showerror("Validation Error", "Leverage must be between 0 and 500")
                return False
                
            if self.order_type_var.get() in ["LIMIT", "STOP_LIMIT"]:
                price = float(self.price_var.get())
                if price <= 0:
                    messagebox.showerror("Validation Error", "Price must be greater than 0")
                    return False
                    
            if self.order_type_var.get() in ["STOP_MARKET", "STOP_LIMIT"]:
                stop_price = float(self.stop_price_var.get())
                if stop_price <= 0:
                    messagebox.showerror("Validation Error", "Stop Price must be greater than 0")
                    return False
                    
            if not self.strategy_id_var.get().strip():
                messagebox.showerror("Validation Error", "Strategy ID is required")
                return False
                
            if not self.symbol_var.get().strip():
                messagebox.showerror("Validation Error", "Symbol is required")
                return False
                
            return True
            
        except ValueError:
            messagebox.showerror("Validation Error", "Invalid numeric values")
            return False
    
    def build_order_payload(self) -> Dict[str, Any]:
        """Build the order payload for the API - matches COM server schema exactly"""
        # Build the order object first
        order_data = {
            "instrument": {
                "class": "crypto_perp",
                "symbol": self.symbol_var.get().strip()
            },
            "side": self.side_var.get(),
            "quantity": {
                "type": "contracts",
                "value": float(self.quantity_var.get())
            },
            "order_type": self.order_type_var.get(),
            "time_in_force": self.tif_var.get(),
            "flags": {
                "post_only": self.post_only_var.get(),
                "reduce_only": self.reduce_only_var.get(),
                "hidden": False,
                "iceberg": {},
                "allow_partial_fills": True
            },
            "routing": {
                "mode": "AUTO"
            },
            "leverage": {
                "enabled": float(self.leverage_var.get()) > 1.0,
                "leverage": float(self.leverage_var.get()) if float(self.leverage_var.get()) > 1.0 else None
            }
        }
        
        # Add price for non-market orders
        if self.order_type_var.get() != "MARKET":
            order_data["price"] = float(self.price_var.get())
            
        # Add stop price for stop orders
        if self.order_type_var.get() in ["STOP_MARKET", "STOP_LIMIT"]:
            order_data["stop_price"] = float(self.stop_price_var.get())
        
        # Build the complete payload matching COM server schema
        payload = {
            "idempotency_key": self.idempotency_key_var.get().strip(),
            "environment": {
                "sandbox": self.paper_trade.get()
            },
            "source": {
                "strategy_id": self.strategy_id_var.get().strip(),
                "instance_id": "gui_instance_001",
                "owner": "gui_user"
            },
            "order": order_data
        }
        
        # Add notes if provided
        if self.notes_var.get().strip():
            payload["notes"] = self.notes_var.get().strip()
            
        return payload
    
    def generate_hmac_signature(self, method: str, path: str, body: str, timestamp: str) -> str:
        """Generate HMAC signature for request authentication"""
        try:
            # Create signature base string exactly as server expects
            # Format: timestamp\nmethod\npath\nbody
            base_string = f"{timestamp}\n{method}\n{path}\n{body}"
            
            print(f"🔐 Generating HMAC signature:")
            print(f"  Secret Key: {self.secret_key[:20]}...")
            print(f"  Timestamp: {timestamp}")
            print(f"  Method: {method}")
            print(f"  Path: {path}")
            print(f"  Body: {body[:50]}...")
            print(f"  Base String: {repr(base_string)}")
            
            # Generate HMAC-SHA256 signature using the secret key directly (no salt)
            signature = hmac.new(
                self.secret_key.encode('utf-8'),
                base_string.encode('utf-8'),
                hashlib.sha256
            ).hexdigest()
            
            print(f"  Generated signature: {signature[:20]}...")
            return signature
            
        except Exception as e:
            print(f"❌ Error generating HMAC signature: {e}")
            return ""
    
    def create_authorization_header(self, method: str, path: str, body: str, timestamp: str) -> str:
        """Create the Authorization header in the format the server expects"""
        signature = self.generate_hmac_signature(method, path, body, timestamp)
        if not signature:
            return ""
        
        # Format: HMAC key_id="{api_key}", signature="{signature}", ts={timestamp}
        auth_header = f'HMAC key_id="{self.api_key}", signature="{signature}", ts={timestamp}'
        print(f"  Authorization Header: {auth_header[:50]}...")
        return auth_header
    
    def test_connection(self):
        """Test connection to COM server"""
        try:
            url = f"{self.server_url_var.get()}/health"
            response = requests.get(url, timeout=5)
            
            if response.status_code == 200:
                self.status_label.config(text="🟢 Connected", foreground="green")
                messagebox.showinfo("Connection", "Successfully connected to COM server!")
            else:
                self.status_label.config(text="🟡 Partial", foreground="orange")
                messagebox.showwarning("Connection", f"Server responded with status {response.status_code}")
                
        except requests.exceptions.RequestException as e:
            self.status_label.config(text="🔴 Disconnected", foreground="red")
            messagebox.showerror("Connection Error", f"Failed to connect: {str(e)}")
    
    def save_configuration(self):
        """Save configuration settings"""
        self.com_base_url = self.server_url_var.get()
        self.api_key = self.api_key_var.get()
        self.secret_key = self.secret_key_var.get()
        messagebox.showinfo("Configuration", "Configuration saved successfully!")
    
    def send_order(self):
        """Send the order to the COM server"""
        if not self.validate_form():
            return
            
        # Build payload
        payload = self.build_order_payload()
        
        # Display the payload
        self.response_text.delete(1.0, tk.END)
        self.response_text.insert(tk.END, "Sending order...\n\n")
        self.response_text.insert(tk.END, "Payload:\n")
        self.response_text.insert(tk.END, json.dumps(payload, indent=2))
        self.response_text.insert(tk.END, "\n\n")
        
        # Send order in background thread
        threading.Thread(target=self._send_order_async, args=(payload,), daemon=True).start()
    
    def _send_order_async(self, payload: Dict[str, Any]):
        """Send order asynchronously"""
        try:
            # Try to send to actual COM server first
            if self._send_to_com_server(payload):
                return
                
            # Fallback to simulation if COM server is not available
            self.root.after(1000, lambda: self._simulate_response(payload))
            
        except Exception as e:
            self.root.after(0, lambda: self._show_error(f"Error sending order: {str(e)}"))
    
    def _send_to_com_server(self, payload: Dict[str, Any]) -> bool:
        """Send order to actual COM server"""
        try:
            url = f"{self.com_base_url}/api/v1/orders/orders"
            
            # Prepare payload
            payload_str = json.dumps(payload)
            timestamp = str(int(time.time()))
            
            # Create authorization header
            auth_header = self.create_authorization_header("POST", "/api/v1/orders/orders", payload_str, timestamp)
            if not auth_header:
                print("❌ Failed to create authorization header")
                return False
            
            # Add authentication headers
            headers = {
                "Content-Type": "application/json",
                "Authorization": auth_header
            }
            
            print(f"🔐 Sending request to: {url}")
            print(f"🔑 API Key: {self.api_key[:20]}...")
            print(f"⏰ Timestamp: {timestamp}")
            print(f"📦 Payload: {payload_str[:100]}...")
            print(f"📤 Headers: {headers}")
            
            response = requests.post(url, json=payload, headers=headers, timeout=10)
            
            print(f"📥 Response Status: {response.status_code}")
            print(f"📥 Response Body: {response.text}")
            
            if response.status_code in [200, 201]:
                self.root.after(0, lambda: self._show_com_response(response.json()))
                return True
            else:
                self.root.after(0, lambda: self._show_error(f"Server error: {response.status_code} - {response.text}"))
                return False
                
        except requests.exceptions.RequestException as e:
            print(f"❌ Request exception: {e}")
            # Server not available, fall back to simulation
            return False
        except Exception as e:
            print(f"❌ Unexpected error: {e}")
            return False
    
    def _show_com_response(self, response: Dict[str, Any]):
        """Show response from COM server"""
        self.response_text.insert(tk.END, "COM Server Response:\n")
        self.response_text.insert(tk.END, json.dumps(response, indent=2))
        self.response_text.insert(tk.END, "\n\n")
        
        if response.get("status") == "success":
            self.response_text.insert(tk.END, "✅ Order sent successfully to COM server!\n")
            messagebox.showinfo("Success", "Order sent successfully to COM server!")
            
            # Refresh order history
            self.refresh_order_history()
        else:
            self.response_text.insert(tk.END, "❌ Order failed\n")
            messagebox.showerror("Error", "Order failed")
        
        # Generate new idempotency key for next order
        self.idempotency_key_var.set(self.generate_idempotency_key())
    
    def _simulate_response(self, payload: Dict[str, Any]):
        """Simulate API response for demo purposes"""
        # Simulate successful order creation
        response = {
            "status": "success",
            "message": "Order created successfully (SIMULATED)",
            "data": {
                "order_id": f"ord_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}",
                "status": "NEW",
                "broker_order_id": None,
                "created_at": datetime.now().isoformat(),
                "paper_trade": payload.get("paper_trade", False)
            }
        }
        
        self.response_text.insert(tk.END, "Simulated Response:\n")
        self.response_text.insert(tk.END, json.dumps(response, indent=2))
        self.response_text.insert(tk.END, "\n\n")
        
        if payload.get("paper_trade"):
            self.response_text.insert(tk.END, "✅ PAPER TRADE ORDER - No real money involved\n")
        else:
            self.response_text.insert(tk.END, "⚠️  LIVE TRADE ORDER - Real money will be used\n")
        
        # Generate new idempotency key for next order
        self.idempotency_key_var.set(self.generate_idempotency_key())
        
        messagebox.showinfo("Success", "Order sent successfully! (Simulated)")
    
    def _show_error(self, error_msg: str):
        """Show error message in response area"""
        self.response_text.insert(tk.END, f"Error: {error_msg}\n")
        messagebox.showerror("Error", error_msg)
    
    def refresh_order_history(self):
        """Refresh the order history from COM server"""
        try:
            # Clear existing items
            for item in self.history_tree.get_children():
                self.history_tree.delete(item)
            
            # Try to fetch from COM server
            url = f"{self.com_base_url}/api/v1/orders/orders"
            
            # Generate authentication headers
            timestamp = str(int(time.time()))
            auth_header = self.create_authorization_header("GET", "/api/v1/orders/orders", "", timestamp)
            
            headers = {
                "Authorization": auth_header
            }
            
            response = requests.get(url, headers=headers, timeout=10)
            
            if response.status_code == 200:
                orders = response.json().get("data", [])
                for order in orders[:50]:  # Limit to 50 most recent
                    self.history_tree.insert("", "end", values=(
                        order.get("order_id", ""),
                        order.get("symbol", ""),
                        order.get("side", ""),
                        order.get("order_type", ""),
                        order.get("quantity", ""),
                        order.get("price", ""),
                        order.get("status", ""),
                        order.get("created_at", "")[:19]  # Truncate timestamp
                    ))
            else:
                # Add sample data if server not available
                self._add_sample_history()
                
        except requests.exceptions.RequestException:
            # Add sample data if server not available
            self._add_sample_history()
    
    def _add_sample_history(self):
        """Add sample order history data"""
        sample_orders = [
            ("ord_001", "BTCUSDT", "BUY", "LIMIT", "0.001", "50000", "FILLED", "2024-01-15 10:30:00"),
            ("ord_002", "ETHUSDT", "SELL", "MARKET", "0.01", "3000", "FILLED", "2024-01-15 11:15:00"),
            ("ord_003", "BTCUSDT", "SELL", "STOP_LIMIT", "0.002", "52000", "WORKING", "2024-01-15 12:00:00"),
        ]
        
        for order in sample_orders:
            self.history_tree.insert("", "end", values=order)

    def check_key_status(self):
        """Check and display the current key status"""
        status_msg = f"Current Key Status:\n\n"
        status_msg += f"API Key: {self.api_key[:30]}...\n"
        status_msg += f"Secret Key: {self.secret_key[:30]}...\n\n"
        
        if self.api_key and self.api_key != "your_api_key_here":
            status_msg += "✅ API Key: Loaded\n"
        else:
            status_msg += "❌ API Key: Not loaded\n"
            
        if self.secret_key and self.secret_key != "your_secret_key_here":
            status_msg += "✅ Secret Key: Loaded\n"
        else:
            status_msg += "❌ Secret Key: Not loaded\n"
            
        messagebox.showinfo("Key Status", status_msg)

def main():
    root = tk.Tk()
    app = AdvancedOrderFormGUI(root)
    root.mainloop()

if __name__ == "__main__":
    main()
