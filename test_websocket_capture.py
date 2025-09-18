#!/usr/bin/env python3
"""
Capture WebSocket messages for documentation
Non-interactive test to capture all message formats
"""
import asyncio
import websockets
import json
import hmac
import hashlib
import time
import logging
import aiohttp
from typing import Dict, Any, List

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class WebSocketMessageCapture:
    """Capture WebSocket messages for documentation"""
    
    def __init__(self, api_key: str, secret_key: str):
        self.api_key = api_key
        self.secret_key = secret_key
        self.base_url = "http://localhost:8000"
        self.websocket = None
        self.captured_messages = []
        
    def create_hmac_signature(self, timestamp: int, method: str, path: str, body: str) -> str:
        """Create HMAC signature for API requests"""
        base_string = f"{timestamp}\n{method}\n{path}\n{body}"
        signature = hmac.new(
            self.secret_key.encode('utf-8'),
            base_string.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        return signature
    
    def create_websocket_signature(self, timestamp: int, key_id: str) -> str:
        """Create HMAC signature for WebSocket authentication"""
        data_string = f"{key_id}\n{timestamp}"
        signature = hmac.new(
            self.secret_key.encode('utf-8'),
            data_string.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        return signature
    
    async def create_test_order(self, strategy_id: str) -> Dict[str, Any]:
        """Create a test order to trigger events"""
        try:
            method = "POST"
            path = "/api/v1/orders/orders"
            timestamp = int(time.time())
            
            payload = {
                "idempotency_key": f"ws_capture_{strategy_id}_{timestamp}",
                "environment": {"sandbox": True},
                "source": {
                    "strategy_id": strategy_id,
                    "instance_id": "ws_capture",
                    "owner": "test_user"
                },
                "order": {
                    "instrument": {"class": "crypto_perp", "symbol": "BTC_USDT"},
                    "side": "BUY",
                    "quantity": {"type": "contracts", "value": 0.0001},
                    "order_type": "MARKET",
                    "time_in_force": "IOC",
                    "flags": {
                        "post_only": False,
                        "reduce_only": False,
                        "hidden": False,
                        "iceberg": {},
                        "allow_partial_fills": True
                    },
                    "routing": {"mode": "AUTO"},
                    "leverage": {"enabled": False}
                }
            }
            
            body = json.dumps(payload)
            signature = self.create_hmac_signature(timestamp, method, path, body)
            
            headers = {
                "Authorization": f'HMAC key_id="{self.api_key}", signature="{signature}", ts={timestamp}',
                "Content-Type": "application/json"
            }
            
            url = f"{self.base_url}{path}"
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, headers=headers) as response:
                    result = await response.json()
                    return result
                    
        except Exception as e:
            logger.error(f"❌ Error creating test order: {e}")
            return {"error": str(e)}
    
    async def connect_and_capture(self, strategy_id: str = "test_strategy"):
        """Connect to WebSocket and capture messages"""
        try:
            # Connect to WebSocket
            uri = "ws://localhost:8000/api/v1/stream"
            logger.info(f"🔌 Connecting to WebSocket: {uri}")
            
            self.websocket = await websockets.connect(uri)
            logger.info("✅ WebSocket connected")
            
            # Step 1: Authenticate
            timestamp = int(time.time())
            signature = self.create_websocket_signature(timestamp, self.api_key)
            
            auth_msg = {
                "type": "AUTH",
                "key_id": self.api_key,
                "ts": timestamp,
                "signature": signature
            }
            
            logger.info("🔐 Authenticating...")
            await self.websocket.send(json.dumps(auth_msg))
            
            auth_response = await self.websocket.recv()
            auth_data = json.loads(auth_response)
            self.captured_messages.append({
                "direction": "received",
                "type": "AUTH_RESPONSE",
                "message": auth_data
            })
            
            if auth_data.get("status") != "AUTH_ACK":
                raise Exception(f"Authentication failed: {auth_data}")
            
            logger.info("✅ Authentication successful")
            
            # Step 2: Subscribe to strategy
            subscribe_msg = {
                "type": "SUBSCRIBE",
                "strategy_id": strategy_id
            }
            
            logger.info(f"📡 Subscribing to strategy: {strategy_id}")
            await self.websocket.send(json.dumps(subscribe_msg))
            
            sub_response = await self.websocket.recv()
            sub_data = json.loads(sub_response)
            self.captured_messages.append({
                "direction": "received",
                "type": "SUBSCRIBE_RESPONSE",
                "message": sub_data
            })
            
            if sub_data.get("status") != "SUBSCRIBED":
                raise Exception(f"Subscription failed: {sub_data}")
            
            logger.info("✅ Subscription successful")
            
            # Step 3: Create test order to trigger events
            logger.info("📤 Creating test order to trigger events...")
            order_result = await self.create_test_order(strategy_id)
            
            if "error" in order_result:
                logger.error(f"❌ Failed to create test order: {order_result['error']}")
            else:
                logger.info(f"✅ Test order created: {order_result.get('order_ref')}")
            
            # Step 4: Capture events for 15 seconds
            logger.info("👂 Capturing events for 15 seconds...")
            start_time = time.time()
            
            while time.time() - start_time < 15:
                try:
                    message = await asyncio.wait_for(self.websocket.recv(), timeout=1.0)
                    event = json.loads(message)
                    
                    self.captured_messages.append({
                        "direction": "received",
                        "type": "EVENT",
                        "message": event
                    })
                    
                    event_type = event.get("event_type", "UNKNOWN")
                    order_ref = event.get("order_ref", "N/A")
                    logger.info(f"📨 Captured event: {event_type} - {order_ref}")
                    
                except asyncio.TimeoutError:
                    continue
                except Exception as e:
                    logger.error(f"❌ Error receiving message: {e}")
                    break
            
            logger.info(f"✅ Captured {len(self.captured_messages)} messages")
            
        except Exception as e:
            logger.error(f"❌ WebSocket capture failed: {e}")
            raise
        finally:
            if self.websocket:
                await self.websocket.close()
                logger.info("🔌 WebSocket disconnected")
    
    def save_captured_messages(self, filename: str = "captured_websocket_messages.json"):
        """Save captured messages to file"""
        try:
            with open(filename, 'w') as f:
                json.dump(self.captured_messages, f, indent=2)
            logger.info(f"💾 Saved captured messages to {filename}")
        except Exception as e:
            logger.error(f"❌ Error saving messages: {e}")
    
    def print_message_summary(self):
        """Print summary of captured messages"""
        print("\n📊 CAPTURED WEBSOCKET MESSAGES SUMMARY")
        print("=" * 50)
        
        for i, msg in enumerate(self.captured_messages, 1):
            direction = msg["direction"]
            msg_type = msg["type"]
            message = msg["message"]
            
            print(f"\n{i}. {direction.upper()} - {msg_type}")
            print(f"   Content: {json.dumps(message, indent=4)}")

async def main():
    """Main capture function"""
    print("🧪 WebSocket Message Capture Test")
    print("=" * 50)
    
    # Load API keys
    try:
        with open("keys/test_strategy_keys.json", "r") as f:
            keys = json.load(f)
        api_key = keys["api_key"]
        secret_key = keys["secret_key"]
    except FileNotFoundError:
        logger.error("❌ API keys file not found. Run 'python quick_generate_keys.py' first.")
        return
    except Exception as e:
        logger.error(f"❌ Error loading API keys: {e}")
        return
    
    # Create capture instance
    capture = WebSocketMessageCapture(api_key, secret_key)
    
    try:
        # Connect and capture messages
        await capture.connect_and_capture("test_strategy")
        
        # Print summary
        capture.print_message_summary()
        
        # Save to file
        capture.save_captured_messages()
        
        print("\n✅ WebSocket message capture completed!")
        print("💾 Messages saved to 'captured_websocket_messages.json'")
        
    except Exception as e:
        logger.error(f"❌ Capture failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 Capture stopped by user")
    except Exception as e:
        print(f"❌ Capture failed: {e}")
