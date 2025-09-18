#!/usr/bin/env python3
"""
Test WebSocket connection for algo monitoring
Tests position and order updates for specific algo IDs
"""
import asyncio
import websockets
import json
import hmac
import hashlib
import time
import logging
from typing import Optional, Dict, Any

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class AlgoWebSocketMonitor:
    """WebSocket client for algo monitoring"""
    
    def __init__(self, api_key: str, secret_key: str, algo_id: str):
        self.api_key = api_key
        self.secret_key = secret_key
        self.algo_id = algo_id
        self.websocket: Optional[websockets.WebSocketClientProtocol] = None
        self.running = False
        self.connection_id = f"algo_{algo_id}_{int(time.time())}"
        
    def create_websocket_signature(self, timestamp: int, key_id: str) -> str:
        """Create HMAC signature for WebSocket authentication"""
        data_string = f"{key_id}\n{timestamp}"
        signature = hmac.new(
            self.secret_key.encode('utf-8'),
            data_string.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        return signature
    
    async def connect_and_monitor(self):
        """Connect to WebSocket and start monitoring"""
        try:
            # Connect to WebSocket
            uri = "ws://localhost:8000/api/v1/stream"
            logger.info(f"🔌 Connecting to WebSocket: {uri}")
            self.websocket = await websockets.connect(uri)
            self.running = True
            logger.info("✅ WebSocket connected successfully")
            
            # Step 1: Authenticate
            await self.authenticate()
            
            # Step 2: Subscribe to algo events
            await self.subscribe_to_algo()
            
            # Step 3: Start monitoring loop
            await self.monitor_events()
            
        except Exception as e:
            logger.error(f"❌ WebSocket connection failed: {e}")
            raise
        finally:
            await self.disconnect()
    
    async def authenticate(self):
        """Authenticate with the WebSocket server"""
        try:
            timestamp = int(time.time())
            signature = self.create_websocket_signature(timestamp, self.api_key)
            
            auth_msg = {
                "type": "AUTH",
                "key_id": self.api_key,
                "ts": timestamp,
                "signature": signature
            }
            
            logger.info(f"🔐 Authenticating with algo ID: {self.algo_id}")
            logger.info(f"📤 Auth message: {json.dumps(auth_msg, indent=2)}")
            
            await self.websocket.send(json.dumps(auth_msg))
            auth_response = await self.websocket.recv()
            auth_data = json.loads(auth_response)
            
            logger.info(f"📥 Auth response: {json.dumps(auth_data, indent=2)}")
            
            if auth_data.get("status") != "AUTH_ACK":
                raise Exception(f"Authentication failed: {auth_data}")
            
            logger.info("✅ Authentication successful")
            
        except Exception as e:
            logger.error(f"❌ Authentication failed: {e}")
            raise
    
    async def subscribe_to_algo(self):
        """Subscribe to events for this algo ID"""
        try:
            subscribe_msg = {
                "type": "SUBSCRIBE",
                "strategy_id": self.algo_id
            }
            
            logger.info(f"📡 Subscribing to algo events: {self.algo_id}")
            logger.info(f"📤 Subscribe message: {json.dumps(subscribe_msg, indent=2)}")
            
            await self.websocket.send(json.dumps(subscribe_msg))
            sub_response = await self.websocket.recv()
            sub_data = json.loads(sub_response)
            
            logger.info(f"📥 Subscribe response: {json.dumps(sub_data, indent=2)}")
            
            if sub_data.get("status") != "SUBSCRIBED":
                raise Exception(f"Subscription failed: {sub_data}")
            
            logger.info(f"✅ Successfully subscribed to algo: {self.algo_id}")
            
        except Exception as e:
            logger.error(f"❌ Subscription failed: {e}")
            raise
    
    async def monitor_events(self):
        """Monitor events for the subscribed algo"""
        logger.info(f"👂 Starting event monitoring for algo: {self.algo_id}")
        logger.info("📊 Listening for position and order updates...")
        logger.info("💡 Send a test order to see events in action!")
        logger.info("🛑 Press Ctrl+C to stop monitoring")
        
        try:
            async for message in self.websocket:
                try:
                    event = json.loads(message)
                    await self.handle_event(event)
                except json.JSONDecodeError as e:
                    logger.error(f"❌ Failed to parse message: {e}")
                    logger.error(f"Raw message: {message}")
                except Exception as e:
                    logger.error(f"❌ Error handling event: {e}")
                    
        except websockets.exceptions.ConnectionClosed:
            logger.warning("🔌 WebSocket connection closed")
        except KeyboardInterrupt:
            logger.info("🛑 Monitoring stopped by user")
        except Exception as e:
            logger.error(f"❌ Monitoring error: {e}")
    
    async def handle_event(self, event: Dict[str, Any]):
        """Handle incoming WebSocket events"""
        event_type = event.get("event_type", "UNKNOWN")
        order_ref = event.get("order_ref", "N/A")
        position_ref = event.get("position_ref", "N/A")
        details = event.get("details", {})
        
        # Color coding for different event types
        if event_type == "ORDER_UPDATE":
            logger.info(f"📋 ORDER UPDATE - Order: {order_ref}")
            logger.info(f"   State: {event.get('state', 'N/A')}")
            if details:
                logger.info(f"   Details: {json.dumps(details, indent=4)}")
                
        elif event_type == "FILL":
            logger.info(f"💰 FILL - Order: {order_ref}")
            logger.info(f"   Position: {position_ref}")
            if details:
                logger.info(f"   Details: {json.dumps(details, indent=4)}")
                
        elif event_type == "CANCELLED":
            logger.info(f"❌ CANCELLED - Order: {order_ref}")
            logger.info(f"   Position: {position_ref}")
            if details:
                logger.info(f"   Details: {json.dumps(details, indent=4)}")
                
        elif event_type == "POSITION_UPDATE":
            logger.info(f"📊 POSITION UPDATE - Position: {position_ref}")
            if details:
                logger.info(f"   Details: {json.dumps(details, indent=4)}")
                
        elif event_type == "STOP_TRIGGERED":
            logger.info(f"🛑 STOP TRIGGERED - Order: {order_ref}")
            logger.info(f"   Position: {position_ref}")
            if details:
                logger.info(f"   Details: {json.dumps(details, indent=4)}")
                
        elif event_type == "TAKE_PROFIT_TRIGGERED":
            logger.info(f"🎯 TAKE PROFIT TRIGGERED - Order: {order_ref}")
            logger.info(f"   Position: {position_ref}")
            if details:
                logger.info(f"   Details: {json.dumps(details, indent=4)}")
                
        elif event_type == "HEARTBEAT":
            logger.debug(f"💓 HEARTBEAT - {details.get('timestamp', 'N/A')}")
            
        else:
            logger.info(f"❓ UNKNOWN EVENT - Type: {event_type}")
            logger.info(f"   Full event: {json.dumps(event, indent=2)}")
    
    async def disconnect(self):
        """Disconnect from WebSocket"""
        if self.websocket:
            await self.websocket.close()
            logger.info("🔌 WebSocket disconnected")
        self.running = False

def load_api_keys():
    """Load API keys from generated file"""
    try:
        with open("keys/test_strategy_keys.json", "r") as f:
            keys = json.load(f)
        return keys["api_key"], keys["secret_key"]
    except FileNotFoundError:
        logger.error("❌ API keys file not found. Run 'python quick_generate_keys.py' first.")
        return None, None
    except Exception as e:
        logger.error(f"❌ Error loading API keys: {e}")
        return None, None

async def test_multiple_algos():
    """Test monitoring multiple algo IDs simultaneously"""
    api_key, secret_key = load_api_keys()
    if not api_key or not secret_key:
        return
    
    # Test with different algo IDs
    algo_ids = ["test_strategy", "algo_001", "algo_002"]
    
    logger.info(f"🚀 Starting monitoring for {len(algo_ids)} algos: {algo_ids}")
    
    # Create monitoring tasks
    tasks = []
    for algo_id in algo_ids:
        monitor = AlgoWebSocketMonitor(api_key, secret_key, algo_id)
        task = asyncio.create_task(monitor.connect_and_monitor())
        tasks.append(task)
    
    try:
        # Run all monitoring tasks concurrently
        await asyncio.gather(*tasks)
    except KeyboardInterrupt:
        logger.info("🛑 Stopping all monitors...")
        for task in tasks:
            task.cancel()
    except Exception as e:
        logger.error(f"❌ Error in multi-algo monitoring: {e}")

async def test_single_algo():
    """Test monitoring a single algo ID"""
    api_key, secret_key = load_api_keys()
    if not api_key or not secret_key:
        return
    
    # Get algo ID from user input
    algo_id = input("Enter algo ID to monitor (or press Enter for 'test_strategy'): ").strip()
    if not algo_id:
        algo_id = "test_strategy"
    
    logger.info(f"🚀 Starting monitoring for algo: {algo_id}")
    
    monitor = AlgoWebSocketMonitor(api_key, secret_key, algo_id)
    await monitor.connect_and_monitor()

async def main():
    """Main test function"""
    print("🧪 WebSocket Algo Monitoring Test")
    print("=" * 50)
    
    # Check if COM system is running
    try:
        import requests
        response = requests.get("http://localhost:8000/health", timeout=5)
        if response.status_code == 200:
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
    print("1. Monitor single algo")
    print("2. Monitor multiple algos")
    
    choice = input("Enter choice (1 or 2): ").strip()
    
    if choice == "1":
        await test_single_algo()
    elif choice == "2":
        await test_multiple_algos()
    else:
        print("❌ Invalid choice")
        return

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 Test stopped by user")
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
