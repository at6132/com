#!/usr/bin/env python3
"""
Simple WebSocket connection test
Quick test to verify WebSocket authentication and basic functionality
"""
import asyncio
import websockets
import json
import hmac
import hashlib
import time
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def test_websocket_connection():
    """Test basic WebSocket connection and authentication"""
    
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
    
    try:
        # Connect to WebSocket
        uri = "ws://localhost:8000/api/v1/stream"
        logger.info(f"🔌 Connecting to WebSocket: {uri}")
        
        async with websockets.connect(uri) as websocket:
            logger.info("✅ WebSocket connected successfully")
            
            # Step 1: Authenticate
            timestamp = int(time.time())
            data_string = f"{api_key}\n{timestamp}"
            signature = hmac.new(
                secret_key.encode('utf-8'),
                data_string.encode('utf-8'),
                hashlib.sha256
            ).hexdigest()
            
            auth_msg = {
                "type": "AUTH",
                "key_id": api_key,
                "ts": timestamp,
                "signature": signature
            }
            
            logger.info("🔐 Sending authentication...")
            await websocket.send(json.dumps(auth_msg))
            
            auth_response = await websocket.recv()
            auth_data = json.loads(auth_response)
            logger.info(f"📥 Auth response: {json.dumps(auth_data, indent=2)}")
            
            if auth_data.get("status") != "AUTH_ACK":
                logger.error(f"❌ Authentication failed: {auth_data}")
                return
            
            logger.info("✅ Authentication successful")
            
            # Step 2: Subscribe to test strategy
            strategy_id = "test_strategy"
            subscribe_msg = {
                "type": "SUBSCRIBE",
                "strategy_id": strategy_id
            }
            
            logger.info(f"📡 Subscribing to strategy: {strategy_id}")
            await websocket.send(json.dumps(subscribe_msg))
            
            sub_response = await websocket.recv()
            sub_data = json.loads(sub_response)
            logger.info(f"📥 Subscribe response: {json.dumps(sub_data, indent=2)}")
            
            if sub_data.get("status") != "SUBSCRIBED":
                logger.error(f"❌ Subscription failed: {sub_data}")
                return
            
            logger.info("✅ Subscription successful")
            
            # Step 3: Listen for a few seconds
            logger.info("👂 Listening for events (10 seconds)...")
            logger.info("💡 In another terminal, run 'python test_trigger_events.py' to generate events")
            
            timeout = 10  # Listen for 10 seconds
            start_time = time.time()
            
            while time.time() - start_time < timeout:
                try:
                    # Wait for message with timeout
                    message = await asyncio.wait_for(websocket.recv(), timeout=1.0)
                    event = json.loads(message)
                    
                    event_type = event.get("event_type", "UNKNOWN")
                    order_ref = event.get("order_ref", "N/A")
                    
                    if event_type == "HEARTBEAT":
                        logger.debug(f"💓 Heartbeat received")
                    else:
                        logger.info(f"📨 Event received: {event_type} - Order: {order_ref}")
                        logger.info(f"   Full event: {json.dumps(event, indent=2)}")
                        
                except asyncio.TimeoutError:
                    # No message received in this second, continue
                    continue
                except Exception as e:
                    logger.error(f"❌ Error receiving message: {e}")
                    break
            
            logger.info("✅ WebSocket test completed successfully")
            logger.info("🎉 Your WebSocket connection is working!")
            
    except websockets.exceptions.ConnectionRefused:
        logger.error("❌ Connection refused. Is the COM system running?")
        logger.error("💡 Run 'python start_com_system.py' first")
    except Exception as e:
        logger.error(f"❌ WebSocket test failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    print("🧪 Simple WebSocket Connection Test")
    print("=" * 50)
    
    try:
        asyncio.run(test_websocket_connection())
    except KeyboardInterrupt:
        print("\n🛑 Test stopped by user")
    except Exception as e:
        print(f"❌ Test failed: {e}")
