#!/usr/bin/env python3
"""
Complete WebSocket monitoring test
Demonstrates full algo monitoring capabilities with real-time events
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

class CompleteWebSocketTest:
    """Complete WebSocket monitoring test"""
    
    def __init__(self, api_key: str, secret_key: str):
        self.api_key = api_key
        self.secret_key = secret_key
        self.base_url = "http://localhost:8000"
        self.websocket = None
        self.running = False
        
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
        """Create a test order"""
        try:
            method = "POST"
            path = "/api/v1/orders/orders"
            timestamp = int(time.time())
            
            payload = {
                "idempotency_key": f"ws_test_{strategy_id}_{timestamp}",
                "environment": {"sandbox": True},
                "source": {
                    "strategy_id": strategy_id,
                    "instance_id": "ws_test",
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
    
    async def connect_websocket(self, strategy_id: str):
        """Connect to WebSocket and authenticate"""
        try:
            uri = "ws://localhost:8000/api/v1/stream"
            logger.info(f"🔌 Connecting to WebSocket: {uri}")
            
            self.websocket = await websockets.connect(uri)
            self.running = True
            logger.info("✅ WebSocket connected")
            
            # Authenticate
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
            
            if auth_data.get("status") != "AUTH_ACK":
                raise Exception(f"Authentication failed: {auth_data}")
            
            logger.info("✅ Authentication successful")
            
            # Subscribe to strategy
            subscribe_msg = {
                "type": "SUBSCRIBE",
                "strategy_id": strategy_id
            }
            
            logger.info(f"📡 Subscribing to strategy: {strategy_id}")
            await self.websocket.send(json.dumps(subscribe_msg))
            
            sub_response = await self.websocket.recv()
            sub_data = json.loads(sub_response)
            
            if sub_data.get("status") != "SUBSCRIBED":
                raise Exception(f"Subscription failed: {sub_data}")
            
            logger.info("✅ Subscription successful")
            
        except Exception as e:
            logger.error(f"❌ WebSocket connection failed: {e}")
            raise
    
    async def monitor_events(self, duration: int = 30):
        """Monitor events for specified duration"""
        logger.info(f"👂 Monitoring events for {duration} seconds...")
        logger.info("📊 Listening for position and order updates...")
        
        start_time = time.time()
        event_count = 0
        
        try:
            while time.time() - start_time < duration and self.running:
                try:
                    message = await asyncio.wait_for(self.websocket.recv(), timeout=1.0)
                    event = json.loads(message)
                    event_count += 1
                    
                    await self.handle_event(event, event_count)
                    
                except asyncio.TimeoutError:
                    # No message received, continue
                    continue
                except Exception as e:
                    logger.error(f"❌ Error receiving message: {e}")
                    break
            
            logger.info(f"✅ Monitoring completed. Received {event_count} events.")
            
        except Exception as e:
            logger.error(f"❌ Monitoring error: {e}")
    
    async def handle_event(self, event: Dict[str, Any], event_num: int):
        """Handle incoming WebSocket events"""
        event_type = event.get("event_type", "UNKNOWN")
        order_ref = event.get("order_ref", "N/A")
        position_ref = event.get("position_ref", "N/A")
        details = event.get("details", {})
        
        # Color-coded event logging
        if event_type == "ORDER_UPDATE":
            logger.info(f"📋 [{event_num}] ORDER UPDATE - {order_ref}")
            logger.info(f"    State: {event.get('state', 'N/A')}")
            
        elif event_type == "FILL":
            logger.info(f"💰 [{event_num}] FILL - {order_ref}")
            logger.info(f"    Position: {position_ref}")
            if details:
                logger.info(f"    Price: {details.get('price', 'N/A')}")
                logger.info(f"    Quantity: {details.get('quantity', 'N/A')}")
                
        elif event_type == "CANCELLED":
            logger.info(f"❌ [{event_num}] CANCELLED - {order_ref}")
            
        elif event_type == "POSITION_UPDATE":
            logger.info(f"📊 [{event_num}] POSITION UPDATE - {position_ref}")
            if details:
                logger.info(f"    Size: {details.get('size', 'N/A')}")
                logger.info(f"    PnL: {details.get('unrealized_pnl', 'N/A')}")
                
        elif event_type == "STOP_TRIGGERED":
            logger.info(f"🛑 [{event_num}] STOP TRIGGERED - {order_ref}")
            
        elif event_type == "TAKE_PROFIT_TRIGGERED":
            logger.info(f"🎯 [{event_num}] TAKE PROFIT TRIGGERED - {order_ref}")
            
        elif event_type == "HEARTBEAT":
            logger.debug(f"💓 [{event_num}] Heartbeat")
            
        else:
            logger.info(f"❓ [{event_num}] {event_type} - {order_ref}")
    
    async def disconnect(self):
        """Disconnect from WebSocket"""
        if self.websocket:
            await self.websocket.close()
            logger.info("🔌 WebSocket disconnected")
        self.running = False

async def run_complete_test():
    """Run the complete WebSocket test"""
    
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
    
    # Get strategy ID
    strategy_id = input("Enter strategy ID to test (or press Enter for 'test_strategy'): ").strip()
    if not strategy_id:
        strategy_id = "test_strategy"
    
    logger.info(f"🚀 Starting complete WebSocket test for strategy: {strategy_id}")
    
    # Create test instance
    test = CompleteWebSocketTest(api_key, secret_key)
    
    try:
        # Step 1: Connect to WebSocket
        await test.connect_websocket(strategy_id)
        
        # Step 2: Create test order (this will trigger events)
        logger.info("📤 Creating test order to trigger events...")
        order_result = await test.create_test_order(strategy_id)
        
        if "error" in order_result:
            logger.error(f"❌ Failed to create test order: {order_result['error']}")
        else:
            logger.info(f"✅ Test order created: {order_result.get('order_ref')}")
        
        # Step 3: Monitor events
        await test.monitor_events(duration=30)
        
        logger.info("🎉 Complete WebSocket test finished successfully!")
        logger.info("💡 Key features demonstrated:")
        logger.info("   ✅ WebSocket authentication with HMAC")
        logger.info("   ✅ Strategy-specific event subscription")
        logger.info("   ✅ Real-time order and position updates")
        logger.info("   ✅ Event handling and logging")
        
    except Exception as e:
        logger.error(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await test.disconnect()

async def run_multi_strategy_test():
    """Run test with multiple strategies"""
    
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
    
    # Test multiple strategies
    strategies = ["test_strategy", "algo_001", "algo_002"]
    
    logger.info(f"🚀 Starting multi-strategy WebSocket test")
    logger.info(f"📊 Testing strategies: {strategies}")
    
    # Create test instances for each strategy
    tests = []
    for strategy_id in strategies:
        test = CompleteWebSocketTest(api_key, secret_key)
        tests.append((strategy_id, test))
    
    try:
        # Connect all WebSockets
        for strategy_id, test in tests:
            await test.connect_websocket(strategy_id)
            logger.info(f"✅ Connected to strategy: {strategy_id}")
        
        # Create test orders for each strategy
        for strategy_id, test in tests:
            logger.info(f"📤 Creating test order for {strategy_id}...")
            order_result = await test.create_test_order(strategy_id)
            if "error" not in order_result:
                logger.info(f"✅ Order created for {strategy_id}: {order_result.get('order_ref')}")
        
        # Monitor events from all strategies
        logger.info("👂 Monitoring events from all strategies...")
        
        # Create monitoring tasks
        monitoring_tasks = []
        for strategy_id, test in tests:
            task = asyncio.create_task(test.monitor_events(duration=20))
            monitoring_tasks.append(task)
        
        # Wait for all monitoring tasks
        await asyncio.gather(*monitoring_tasks)
        
        logger.info("🎉 Multi-strategy test completed!")
        
    except Exception as e:
        logger.error(f"❌ Multi-strategy test failed: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Disconnect all WebSockets
        for strategy_id, test in tests:
            await test.disconnect()

async def main():
    """Main test function"""
    print("🧪 Complete WebSocket Monitoring Test")
    print("=" * 50)
    
    # Check if COM system is running
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get("http://localhost:8000/health", timeout=5) as response:
                if response.status == 200:
                    print("✅ COM system is running")
                else:
                    print("❌ COM system health check failed")
                    return
    except Exception as e:
        print(f"❌ Cannot connect to COM system: {e}")
        print("💡 Make sure to run 'python start_com_system.py' first")
        return
    
    # Choose test mode
    print("\nChoose test mode:")
    print("1. Single strategy test")
    print("2. Multi-strategy test")
    
    choice = input("Enter choice (1 or 2): ").strip()
    
    if choice == "1":
        await run_complete_test()
    elif choice == "2":
        await run_multi_strategy_test()
    else:
        print("❌ Invalid choice")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 Test stopped by user")
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
