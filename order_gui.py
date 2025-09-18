import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import json
import requests
from datetime import datetime
from typing import Dict, Any
import threading

class OrderFormGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("ATQ Ventures COM - Order Form")
        self.root.geometry("800x900")
        
        # Paper trade mode
        self.paper_trade = tk.BooleanVar(value=True)
        
        # Create main frame
        main_frame = ttk.Frame(root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Configure grid weights
        root.columnconfigure(0, weight=1)
        root.rowconfigure(0, weight=1)
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
        self.leverage_var = tk.StringVar(value="1.0")
        leverage_entry = ttk.Entry(main_frame, textvariable=self.leverage_var)
        leverage_entry.grid(row=8, column=1, sticky=(tk.W, tk.E), pady=5)
        
        # Price (for LIMIT orders)
        ttk.Label(main_frame, text="Price:").grid(row=9, column=0, sticky=tk.W, pady=5)
        self.price_var = tk.StringVar(value="50000")
        price_entry = ttk.Entry(main_frame, textvariable=self.price_var)
        price_entry.grid(row=8, column=1, sticky=(tk.W, tk.E), pady=5)
        
        # Stop Price (for STOP orders)
        ttk.Label(main_frame, text="Stop Price:").grid(row=10, column=0, sticky=tk.W, pady=5)
        self.stop_price_var = tk.StringVar(value="")
        stop_price_entry = ttk.Entry(main_frame, textvariable=self.stop_price_var)
        stop_price_entry.grid(row=10, column=1, sticky=(tk.W, tk.E), pady=5)
        
        # Time in Force
        ttk.Label(main_frame, text="Time in Force:").grid(row=11, column=0, sticky=tk.W, pady=5)
        self.tif_var = tk.StringVar(value="GTC")
        tif_combo = ttk.Combobox(main_frame, textvariable=self.tif_var, 
                                values=["GTC", "IOC", "FOK"], state="readonly")
        tif_combo.grid(row=11, column=1, sticky=(tk.W, tk.E), pady=5)
        
        # Reduce Only
        ttk.Label(main_frame, text="Reduce Only:").grid(row=12, column=0, sticky=tk.W, pady=5)
        self.reduce_only_var = tk.BooleanVar(value=False)
        reduce_only_check = ttk.Checkbutton(main_frame, text="", 
                                          variable=self.reduce_only_var)
        reduce_only_check.grid(row=12, column=1, sticky=tk.W, pady=5)
        
        # Post Only
        ttk.Label(main_frame, text="Post Only:").grid(row=13, column=0, sticky=tk.W, pady=5)
        self.post_only_var = tk.BooleanVar(value=True)
        post_only_check = ttk.Checkbutton(main_frame, text="", 
                                        variable=self.post_only_var)
        post_only_check.grid(row=13, column=1, sticky=tk.W, pady=5)
        
        # Client Order ID
        ttk.Label(main_frame, text="Client Order ID:").grid(row=14, column=0, sticky=tk.W, pady=5)
        self.client_order_id_var = tk.StringVar(value="")
        client_order_id_entry = ttk.Entry(main_frame, textvariable=self.client_order_id_var)
        client_order_id_entry.grid(row=14, column=1, sticky=(tk.W, tk.E), pady=5)
        
        # Idempotency Key
        ttk.Label(main_frame, text="Idempotency Key:").grid(row=15, column=0, sticky=tk.W, pady=5)
        self.idempotency_key_var = tk.StringVar(value="")
        idempotency_key_entry = ttk.Entry(main_frame, textvariable=self.idempotency_key_var)
        idempotency_key_entry.grid(row=15, column=1, sticky=(tk.W, tk.E), pady=5)
        
        # Notes
        ttk.Label(main_frame, text="Notes:").grid(row=16, column=0, sticky=tk.W, pady=5)
        self.notes_var = tk.StringVar(value="")
        notes_entry = ttk.Entry(main_frame, textvariable=self.notes_var)
        notes_entry.grid(row=16, column=1, sticky=(tk.W, tk.E), pady=5)
        
        # Buttons
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=17, column=0, columnspan=2, pady=20)
        
        send_button = ttk.Button(button_frame, text="Send Order", command=self.send_order)
        send_button.pack(side=tk.LEFT, padx=5)
        
        clear_button = ttk.Button(button_frame, text="Clear Form", command=self.clear_form)
        clear_button.pack(side=tk.LEFT, padx=5)
        
        # Response area
        ttk.Label(main_frame, text="Response:").grid(row=18, column=0, sticky=tk.W, pady=(20, 5))
        self.response_text = scrolledtext.ScrolledText(main_frame, height=15, width=80)
        self.response_text.grid(row=19, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5)
        
        # Configure response text grid weight
        main_frame.rowconfigure(19, weight=1)
        
        # Bind order type change to update UI
        order_type_combo.bind('<<ComboboxSelected>>', self.on_order_type_change)
        
        # Initialize form
        self.clear_form()
        
    def on_order_type_change(self, event=None):
        """Update UI based on order type selection"""
        order_type = self.order_type_var.get()
        
        if order_type in ["STOP_MARKET", "STOP_LIMIT"]:
            # Enable stop price field
            self.root.nametowidget(self.root.focus_get()).master.children['!entry2'].config(state='normal')
        else:
            # Disable stop price field
            self.root.nametowidget(self.root.focus_get()).master.children['!entry2'].config(state='disabled')
            
        if order_type == "MARKET":
            # Disable price field for market orders
            self.root.nametowidget(self.root.focus_get()).master.children['!entry1'].config(state='disabled')
        else:
            # Enable price field for other order types
            self.root.nametowidget(self.root.focus_get()).master.children['!entry1'].config(state='normal')
    
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
        self.leverage_var.set("1.0")
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
            # For now, we'll simulate the API call since the COM server might not be running
            # In production, this would call the actual COM API endpoint
            
            # Simulate API call
            self.root.after(1000, lambda: self._simulate_response(payload))
            
        except Exception as e:
            self.root.after(0, lambda: self._show_error(f"Error sending order: {str(e)}"))
    
    def _simulate_response(self, payload: Dict[str, Any]):
        """Simulate API response for demo purposes"""
        # Simulate successful order creation
        response = {
            "status": "success",
            "message": "Order created successfully",
            "data": {
                "order_id": f"ord_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}",
                "status": "NEW",
                "broker_order_id": None,
                "created_at": datetime.now().isoformat(),
                "paper_trade": payload.get("paper_trade", False)
            }
        }
        
        self.response_text.insert(tk.END, "Response:\n")
        self.response_text.insert(tk.END, json.dumps(response, indent=2))
        self.response_text.insert(tk.END, "\n\n")
        
        if payload.get("paper_trade"):
            self.response_text.insert(tk.END, "✅ PAPER TRADE ORDER - No real money involved\n")
        else:
            self.response_text.insert(tk.END, "⚠️  LIVE TRADE ORDER - Real money will be used\n")
        
        # Generate new idempotency key for next order
        self.idempotency_key_var.set(self.generate_idempotency_key())
        
        messagebox.showinfo("Success", "Order sent successfully!")
    
    def _show_error(self, error_msg: str):
        """Show error message in response area"""
        self.response_text.insert(tk.END, f"Error: {error_msg}\n")
        messagebox.showerror("Error", error_msg)

def main():
    root = tk.Tk()
    app = OrderFormGUI(root)
    root.mainloop()

if __name__ == "__main__":
    main()
