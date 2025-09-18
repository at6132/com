# WebSocket Testing for Algo Monitoring

This directory contains comprehensive WebSocket testing scripts for the COM system's real-time algo monitoring capabilities.

## 🚀 Quick Start

1. **Start the COM System:**
   ```bash
   python start_com_system.py
   ```

2. **Generate API Keys (if not done already):**
   ```bash
   python quick_generate_keys.py
   ```

3. **Test WebSocket Connection:**
   ```bash
   python test_websocket_simple.py
   ```

## 📁 Test Scripts

### `test_websocket_simple.py`
- **Purpose:** Basic WebSocket connection test
- **Features:** Authentication, subscription, 10-second monitoring
- **Use Case:** Quick verification that WebSocket is working

### `test_websocket_capture.py`
- **Purpose:** Capture WebSocket messages for documentation
- **Features:** Creates test order, captures all messages
- **Use Case:** Generate message format documentation

### `test_websocket_events.py`
- **Purpose:** Test WebSocket events with exit plans
- **Features:** Creates orders with TP/SL, monitors events
- **Use Case:** Test complex order scenarios

### `test_websocket_complete.py`
- **Purpose:** Complete WebSocket monitoring test
- **Features:** Interactive testing, multiple strategies
- **Use Case:** Full system testing

### `test_websocket_algo_monitoring.py`
- **Purpose:** Algo-specific monitoring
- **Features:** Multiple algo support, real-time monitoring
- **Use Case:** Production-like algo monitoring

### `test_trigger_events.py`
- **Purpose:** Trigger events for WebSocket testing
- **Features:** Creates orders to generate WebSocket events
- **Use Case:** Generate test data for monitoring

## 🔧 WebSocket Connection Flow

1. **Connect:** `ws://localhost:8000/api/v1/stream`
2. **Authenticate:** Send HMAC-signed auth message
3. **Subscribe:** Subscribe to specific strategy ID
4. **Monitor:** Receive real-time events

## 📨 Message Formats

### Authentication
```json
// Client sends:
{
  "type": "AUTH",
  "key_id": "your_api_key",
  "ts": 1234567890,
  "signature": "hmac_signature"
}

// Server responds:
{
  "status": "AUTH_ACK",
  "message": null
}
```

### Subscription
```json
// Client sends:
{
  "type": "SUBSCRIBE",
  "strategy_id": "your_strategy_id"
}

// Server responds:
{
  "status": "SUBSCRIBED",
  "strategy_id": "your_strategy_id",
  "message": null
}
```

## 🎯 Event Types

The WebSocket system broadcasts these event types:

- **ORDER_UPDATE:** Order state changes
- **FILL:** Order execution details
- **POSITION_UPDATE:** Position changes
- **STOP_TRIGGERED:** Stop loss activation
- **TAKE_PROFIT_TRIGGERED:** Take profit activation
- **HEARTBEAT:** Connection health

## 🔐 Authentication

WebSocket authentication uses HMAC-SHA256:

```python
import hmac
import hashlib
import time

def create_websocket_signature(secret_key: str, timestamp: int, key_id: str) -> str:
    data_string = f"{key_id}\n{timestamp}"
    signature = hmac.new(
        secret_key.encode('utf-8'),
        data_string.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()
    return signature
```

## 🧪 Testing Scenarios

### Single Algo Monitoring
```bash
python test_websocket_complete.py
# Choose option 1 for single strategy
```

### Multi-Algo Monitoring
```bash
python test_websocket_complete.py
# Choose option 2 for multiple strategies
```

### Event Generation
```bash
# Terminal 1: Start monitoring
python test_websocket_algo_monitoring.py

# Terminal 2: Generate events
python test_trigger_events.py
```

## 📊 Expected Results

When working correctly, you should see:

1. ✅ WebSocket connection established
2. ✅ Authentication successful (AUTH_ACK)
3. ✅ Subscription successful (SUBSCRIBED)
4. 📨 Real-time events for your strategy
5. 💓 Periodic heartbeat messages

## 🐛 Troubleshooting

### Connection Refused
- Ensure COM system is running: `python start_com_system.py`
- Check port 8000 is available: `netstat -an | findstr :8000`

### Authentication Failed
- Verify API keys exist: `keys/test_strategy_keys.json`
- Check timestamp is recent (within 5 minutes)
- Verify HMAC signature generation

### No Events Received
- Ensure you're subscribed to the correct strategy ID
- Check that orders are being created for that strategy
- Verify event broadcasting is enabled in COM system

## 📝 Notes

- Each algo needs its own WebSocket connection
- Strategy ID must match the algo ID used in orders
- WebSocket connections are persistent until closed
- Events are only sent to subscribed strategies
