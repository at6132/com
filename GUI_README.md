# ATQ Ventures COM - Order Form GUI

This directory contains Python GUI applications for testing orders with the ATQ Ventures Central Order Manager (COM) system.

## Files

- **`launch_gui.py`** - Main launcher that lets you choose between GUI versions
- **`order_gui.py`** - Basic order form with essential features
- **`advanced_order_gui.py`** - Advanced order form with tabs, history, and configuration
- **`generate_keys.py`** - Interactive key generation utility
- **`quick_generate_keys.py`** - Quick key generation script
- **`test_auth.py`** - Authentication testing script
- **`GUI_README.md`** - This documentation file

## 🔑 **API Key Generation (REQUIRED FIRST STEP)**

Before using the GUI, you **MUST** generate secure API keys for authentication:

### **Option 1: Quick Key Generation (Recommended)**
```bash
python quick_generate_keys.py
```
This will:
- Generate secure API keys immediately
- Create a `keys/` directory
- Save keys to JSON files
- Create `.env` templates
- Display the keys for copying

### **Option 2: Interactive Key Generation**
```bash
python generate_keys.py
```
This provides an interactive menu for:
- Generating single or multiple key pairs
- Managing existing keys
- Creating environment templates

### **Option 3: Manual Key Generation**
```bash
python -c "
import secrets, base64
api_key = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode().rstrip('=')
secret_key = base64.urlsafe_b64encode(secrets.token_bytes(64)).decode().rstrip('=')
print(f'API Key: {api_key}')
print(f'Secret Key: {secret_key}')
"
```

## 🚀 **Quick Start**

### **Step 1: Generate Keys**
```bash
python quick_generate_keys.py
```

### **Step 2: Launch GUI**
```bash
python launch_gui.py
```

### **Step 3: Configure Authentication**
1. Go to the **Configuration** tab
2. Click **"Load Keys from File"** and select your generated keys file
3. Or manually copy the API Key and Secret Key from the terminal output
4. Click **"Save Configuration"**

### **Step 4: Test Connection**
1. Click **"Test Connection"** to verify COM server connectivity
2. If successful, you'll see 🟢 Connected status

## 🔐 **Authentication System**

The GUI uses **HMAC-SHA256** authentication with the following headers:

- **`X-API-Key`**: Your generated API key
- **`X-Timestamp`**: Unix timestamp
- **`X-Signature`**: HMAC signature of `timestamp + payload`

### **Security Features**
- **Cryptographically Secure**: Uses `secrets` module for random generation
- **HMAC Signing**: Prevents request tampering
- **Timestamp Validation**: Prevents replay attacks
- **Unique Keys**: Each strategy gets different keys

## 📱 **Features**

### **Basic Order Form** (`order_gui.py`)
- Simple, clean interface
- All essential order parameters
- Paper trade toggle
- Form validation
- Simulated order responses
- Perfect for quick testing

### **Advanced Order Form** (`advanced_order_gui.py`)
- **Order Form Tab**: Full-featured order entry with all parameters
- **Order History Tab**: View order history (connects to COM server when available)
- **Configuration Tab**: Configure COM server connection settings and load API keys
- Real-time connection status
- Automatic fallback to simulation when server is unavailable
- Better error handling and user feedback
- **Automatic Key Loading**: Automatically detects and loads generated keys

## 📋 **Order Parameters**

Both GUIs support the following order parameters:

- **Broker**: Currently MEXC (expandable)
- **Strategy ID**: Your strategy identifier
- **Order Type**: MARKET, LIMIT, STOP_MARKET, STOP_LIMIT
- **Quantity**: Order size
- **Leverage**: Position leverage (1-100x)
- **Price**: Limit price (disabled for market orders)
- **Stop Price**: Stop trigger price (for stop orders)
- **Time in Force**: GTC, IOC, FOK
- **Reduce Only**: Reduce position only
- **Post Only**: Post-only order
- **Client Order ID**: Optional client reference
- **Idempotency Key**: Auto-generated unique identifier
- **Notes**: Additional order notes
- **Paper Trade**: Toggle between paper and live trading

## 🎯 **Advanced Exit Plan System (FULLY IMPLEMENTED)**

The COM system includes a **complete advanced exit plan system** that allows you to define sophisticated take profit (TP) and stop loss (SL) strategies. While the current GUI doesn't expose these fields, the server fully supports them.

### **Exit Plan Capabilities**

- **Multiple TP/SL Legs**: Define multiple take profit and stop loss levels
- **Flexible Allocation**: Specify how much of the position to close at each level
- **Advanced Triggers**: Price-based, percentage-based, trailing, and ratchet triggers
- **Execution Control**: Market, limit, or stop orders for each exit
- **After-Fill Actions**: Automatic actions after each exit (e.g., move SL to breakeven)

### **Exit Plan Schema**

```json
{
  "exit_plan": {
    "legs": [
      {
        "kind": "TP",
        "label": "Take Profit 1",
        "allocation": {
          "type": "percentage",
          "value": 50.0
        },
        "trigger": {
          "mode": "PRICE",
          "price_type": "MARK",
          "value": 55000.0
        },
        "exec": {
          "order_type": "MARKET",
          "time_in_force": "GTC"
        },
        "after_fill_actions": [
          {
            "action": "SET_SL_TO_BREAKEVEN"
          }
        ]
      },
      {
        "kind": "TP",
        "label": "Take Profit 2", 
        "allocation": {
          "type": "percentage",
          "value": 30.0
        },
        "trigger": {
          "mode": "PRICE",
          "price_type": "MARK",
          "value": 60000.0
        },
        "exec": {
          "order_type": "LIMIT",
          "price": 60000.0,
          "time_in_force": "GTC"
        }
      },
      {
        "kind": "SL",
        "label": "Stop Loss",
        "allocation": {
          "type": "percentage", 
          "value": 100.0
        },
        "trigger": {
          "mode": "PRICE",
          "price_type": "MARK",
          "value": 45000.0
        },
        "exec": {
          "order_type": "STOP",
          "stop_price": 45000.0,
          "time_in_force": "GTC"
        }
      }
    ]
  }
}
```

### **Trigger Modes**

- **`PRICE`**: Trigger at specific price level
- **`PERCENT_FROM_ENTRY`**: Trigger at percentage from entry price
- **`TRAIL`**: Trailing stop that follows price movement
- **`RATCHET`**: Ratchet stop that only moves in favorable direction

### **Price Types**

- **`MARK`**: Mark price (mid price)
- **`LAST`**: Last traded price
- **`BID`**: Best bid price
- **`ASK`**: Best ask price
- **`MID`**: Mid price between bid/ask

### **Allocation Types**

- **`percentage`**: Close X% of position
- **`quantity`**: Close specific quantity
- **`notional`**: Close specific notional value

### **After-Fill Actions**

- **`SET_SL_TO_BREAKEVEN`**: Move stop loss to entry price
- **`START_TRAILING_SL`**: Begin trailing stop loss
- **`CREATE_NEW_LEG`**: Create additional exit leg

### **Database Support**

The system automatically tracks:
- ✅ **Orders**: Complete exit plan configuration
- ✅ **Positions**: Position state and exit plan links
- ✅ **SubOrders**: Individual exit leg execution
- ✅ **Fills**: Execution details for each exit

### **API Endpoints**

- **Create Order with Exit Plan**: `POST /api/v1/orders/orders`
- **View Order**: `GET /api/v1/orders/orders/{order_ref}`
- **View Position**: `GET /api/v1/positions/{position_ref}`
- **View SubOrders**: `GET /api/v1/suborders/{position_ref}`

### **Example: Multi-Level TP Strategy**

```json
{
  "order": {
    "instrument": {"class": "crypto_perp", "symbol": "BTC_USDT"},
    "side": "BUY",
    "quantity": {"type": "contracts", "value": 0.001},
    "order_type": "LIMIT",
    "price": 50000.0,
    "time_in_force": "GTC",
    "exit_plan": {
      "legs": [
        {
          "kind": "TP",
          "label": "Quick TP (25%)",
          "allocation": {"type": "percentage", "value": 25.0},
          "trigger": {"mode": "PRICE", "price_type": "MARK", "value": 52000.0},
          "exec": {"order_type": "MARKET", "time_in_force": "GTC"}
        },
        {
          "kind": "TP", 
          "label": "Medium TP (50%)",
          "allocation": {"type": "percentage", "value": 50.0},
          "trigger": {"mode": "PRICE", "price_type": "MARK", "value": 55000.0},
          "exec": {"order_type": "LIMIT", "price": 55000.0, "time_in_force": "GTC"}
        },
        {
          "kind": "TP",
          "label": "Long TP (25%)", 
          "allocation": {"type": "percentage", "value": 25.0},
          "trigger": {"mode": "PRICE", "price_type": "MARK", "value": 60000.0},
          "exec": {"order_type": "LIMIT", "price": 60000.0, "time_in_force": "GTC"}
        },
        {
          "kind": "SL",
          "label": "Stop Loss",
          "allocation": {"type": "percentage", "value": 100.0},
          "trigger": {"mode": "PRICE", "price_type": "MARK", "value": 48000.0},
          "exec": {"order_type": "STOP", "stop_price": 48000.0, "time_in_force": "GTC"}
        }
      ]
    }
  }
}
```

**Note**: The current GUI doesn't expose exit plan fields, but the server fully supports them. You can manually construct exit plan payloads or extend the GUI to include exit plan configuration.

### **Future GUI Enhancements**

To make the exit plan system more accessible, the GUI could be extended with:

- **Exit Plan Tab**: Dedicated tab for configuring TP/SL legs
- **Visual Leg Builder**: Drag-and-drop interface for exit plan construction
- **Template Library**: Pre-built exit plan templates (e.g., "Conservative TP", "Aggressive TP")
- **Real-time Preview**: Live preview of exit plan execution
- **Risk Calculator**: Automatic position sizing based on risk parameters

## 🧪 **Testing Authentication**

### **Test the Authentication System**
```bash
python test_auth.py
```
This script will:
- Load your generated keys
- Create a test order payload
- Generate proper HMAC signatures
- Test connection to COM server
- Verify authentication is working

### **Test with GUI**
1. Generate keys using `quick_generate_keys.py`
2. Launch the advanced GUI: `python advanced_order_gui.py`
3. Go to Configuration tab and load your keys
4. Test connection
5. Send a test order

## 📁 **File Structure After Key Generation**

```
your_project/
├── keys/
│   ├── test_strategy_keys.json          # Generated API keys
│   ├── test_strategy_env_template.env   # Environment template
│   └── all_strategies_*.json           # Combined keys (if multiple)
├── order_gui.py                         # Basic GUI
├── advanced_order_gui.py                # Advanced GUI
├── launch_gui.py                        # GUI launcher
├── generate_keys.py                     # Interactive key generator
├── quick_generate_keys.py               # Quick key generator
├── test_auth.py                         # Authentication tester
└── GUI_README.md                        # This file
```

## 🔒 **Security Best Practices**

### **Key Management**
- ✅ **Generate unique keys** for each strategy/environment
- ✅ **Store keys securely** (not in version control)
- ✅ **Rotate keys regularly** in production
- ✅ **Use different keys** for development/staging/production

### **Environment Security**
- ✅ **Always use paper trading** for testing
- ✅ **Never share API keys** or secret keys
- ✅ **Use HTTPS** in production
- ✅ **Monitor key usage** and revoke compromised keys

## 🚨 **Troubleshooting**

### **Authentication Errors**
- **"Invalid API Key"**: Ensure keys are properly loaded in Configuration tab
- **"Invalid Signature"**: Check that secret key is correct
- **"Timestamp Expired"**: Server clock may be out of sync

### **Connection Issues**
- **"Could not connect"**: COM server not running or wrong URL
- **"Connection refused"**: Check firewall and server status
- **"Timeout"**: Server overloaded or network issues

### **Key Loading Issues**
- **"No keys found"**: Run `quick_generate_keys.py` first
- **"Invalid key format"**: Ensure keys are properly generated
- **"File not found"**: Check keys directory exists

## 🛠️ **Development**

### **Adding New Brokers**
1. Update broker dropdown values in both GUI files
2. Add broker-specific validation logic
3. Implement broker-specific order formatting

### **Customizing Authentication**
- Modify `generate_hmac_signature()` method in advanced GUI
- Add additional security headers as needed
- Implement key rotation logic

### **Extending Order Types**
- Add new order types to dropdown
- Implement validation logic in `validate_form()`
- Update UI state management in `on_order_type_change()`

## 📚 **API Reference**

### **Authentication Headers**
```python
headers = {
    "Content-Type": "application/json",
    "X-API-Key": "your_api_key_here",
    "X-Timestamp": "1234567890",
    "X-Signature": "hmac_sha256_signature"
}
```

### **API Endpoints**
- **Health Check**: `GET /health`
- **Create Order**: `POST /api/v1/orders/orders`
- **Get Orders**: `GET /api/v1/orders/orders`
- **Amend Order**: `POST /api/v1/orders/orders/{order_ref}/amend`
- **Cancel Order**: `POST /api/v1/orders/orders/{order_ref}/cancel`
- **Get Order**: `GET /api/v1/orders/orders/{order_ref}`

### **Order Payload Examples**

#### **Basic Order (Current GUI)**
```json
{
  "idempotency_key": "unique_key_here",
  "environment": {
    "sandbox": true
  },
  "source": {
    "strategy_id": "test_strategy_001",
    "instance_id": "gui_instance_001",
    "owner": "gui_user"
  },
  "order": {
    "instrument": {
      "class": "crypto_perp",
      "symbol": "BTC_USDT"
    },
    "side": "BUY",
    "quantity": {
      "type": "contracts",
      "value": 0.001
    },
    "order_type": "LIMIT",
    "price": 50000.0,
    "time_in_force": "GTC",
    "flags": {
      "post_only": true,
      "reduce_only": false,
      "hidden": false,
      "iceberg": {},
      "allow_partial_fills": true
    },
    "routing": {
      "mode": "AUTO"
    },
    "leverage": {
      "enabled": true,
      "leverage": 10.0
    }
  },
  "notes": "Test order"
}
```

#### **Advanced Order with Exit Plan**
```json
{
  "idempotency_key": "advanced_strategy_001",
  "environment": {
    "sandbox": true
  },
  "source": {
    "strategy_id": "advanced_strategy_001",
    "instance_id": "gui_instance_001",
    "owner": "gui_user"
  },
  "order": {
    "instrument": {
      "class": "crypto_perp",
      "symbol": "BTC_USDT"
    },
    "side": "BUY",
    "quantity": {
      "type": "contracts",
      "value": 0.001
    },
    "order_type": "LIMIT",
    "price": 50000.0,
    "time_in_force": "GTC",
    "flags": {
      "post_only": true,
      "reduce_only": false,
      "hidden": false,
      "iceberg": {},
      "allow_partial_fills": true
    },
    "routing": {
      "mode": "AUTO"
    },
    "leverage": {
      "enabled": true,
      "leverage": 10.0
    },
    "exit_plan": {
      "legs": [
        {
          "kind": "TP",
          "label": "Quick TP (25%)",
          "allocation": {
            "type": "percentage",
            "value": 25.0
          },
          "trigger": {
            "mode": "PRICE",
            "price_type": "MARK",
            "value": 52000.0
          },
          "exec": {
            "order_type": "MARKET",
            "time_in_force": "GTC"
          }
        },
        {
          "kind": "TP",
          "label": "Medium TP (50%)",
          "allocation": {
            "type": "percentage",
            "value": 50.0
          },
          "trigger": {
            "mode": "PRICE",
            "price_type": "MARK",
            "value": 55000.0
          },
          "exec": {
            "order_type": "LIMIT",
            "price": 55000.0,
            "time_in_force": "GTC"
          }
        },
        {
          "kind": "SL",
          "label": "Stop Loss",
          "allocation": {
            "type": "percentage",
            "value": 100.0
          },
          "trigger": {
            "mode": "PRICE",
            "price_type": "MARK",
            "value": 48000.0
          },
          "exec": {
            "order_type": "STOP",
            "stop_price": 48000.0,
            "time_in_force": "GTC"
          }
        }
      ]
    }
  },
  "notes": "Advanced order with exit plan"
}
```

## 🆘 **Support**

For issues or questions:
1. **Check authentication**: Run `python test_auth.py`
2. **Verify keys**: Ensure keys are properly generated and loaded
3. **Check server**: Verify COM server is running and accessible
4. **Review logs**: Check COM server logs for detailed error information
5. **Test with paper trading**: Always test with paper trading mode first

## 📦 **Dependencies**

- **Python 3.6+**
- **tkinter** (usually included with Python)
- **requests** (for HTTP communication)
- **secrets** (for secure key generation)
- **hmac** (for authentication signatures)
- **hashlib** (for SHA256 hashing)

Install missing dependencies:
```bash
pip install requests
```

## 🎯 **Next Steps**

1. **Generate API keys**: `python quick_generate_keys.py`
2. **Test authentication**: `python test_auth.py`
3. **Launch GUI**: `python launch_gui.py`
4. **Configure keys** in the Configuration tab
5. **Test connection** and send orders
6. **Integrate with COM server** when ready
