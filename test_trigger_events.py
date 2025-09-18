#!/usr/bin/env python3
"""
Test script to trigger events for WebSocket monitoring
Creates orders and positions to test real-time updates
"""
import asyncio
import aiohttp
import json
import hmac
import hashlib
import time
import logging
from typing import Dict, Any

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class EventTrigger:
    """Trigger events for WebSocket testing"""
    
    def __init__(self, api_key: str, secret_key: str):
        self.api_key = api_key
        self.secret_key = secret_key
        self.base_url = "http://localhost:8000"
        
    def create_hmac_signature(self, timestamp: int, method: str, path: str, body: str) -> str:
        """Create HMAC signature for API requests"""
        base_string = f"{timestamp}\n{method}\n{path}\n{body}"
        signature = hmac.new(
            self.secret_key.encode('utf-8'),
            base_string.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        return signature
    
    async def create_test_order(self, strategy_id: str, symbol: str = "BTC_USDT") -> Dict[str, Any]:
        """Create a test order to trigger events"""
        try:
            method = "POST"
            path = "/api/v1/orders/orders"
            timestamp = int(time.time())
            
            # Create order payload
            payload = {
                "idempotency_key": f"test_ws_{strategy_id}_{timestamp}",
                "environment": {
                    "sandbox": True
                },
                "source": {
                    "strategy_id": strategy_id,
                    "instance_id": "ws_test",
                    "owner": "test_user"
                },
                "order": {
                    "instrument": {
                        "class": "crypto_perp",
                        "symbol": symbol
                    },
                    "side": "BUY",
                    "quantity": {
                        "type": "contracts",
                        "value": 0.0001
                    },
                    "order_type": "MARKET",
                    "time_in_force": "IOC",
                    "flags": {
                        "post_only": False,
                        "reduce_only": False,
                        "hidden": False,
                        "iceberg": {},
                        "allow_partial_fills": True
                    },
                    "routing": {
                        "mode": "AUTO"
                    },
                    "leverage": {
                        "enabled": False
                    }
                }
            }
            
            body = json.dumps(payload)
            signature = self.create_hmac_signature(timestamp, method, path, body)
            
            headers = {
                "Authorization": f'HMAC key_id="{self.api_key}", signature="{signature}", ts={timestamp}',
                "Content-Type": "application/json"
            }
            
            url = f"{self.base_url}{path}"
            
            logger.info(f"📤 Creating test order for strategy: {strategy_id}")
            logger.info(f"📋 Order details: {symbol} BUY 0.0001 @ MARKET")
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, headers=headers) as response:
                    result = await response.json()
                    
                    if response.status == 200:
                        logger.info(f"✅ Order created successfully: {result.get('order_ref')}")
                        return result
                    else:
                        logger.error(f"❌ Order creation failed: {response.status} - {result}")
                        return {"error": result}
                        
        except Exception as e:
            logger.error(f"❌ Error creating test order: {e}")
            return {"error": str(e)}
    
    async def create_test_order_with_exit_plan(self, strategy_id: str, symbol: str = "BTC_USDT") -> Dict[str, Any]:
        """Create a test order with exit plan to trigger more events"""
        try:
            method = "POST"
            path = "/api/v1/orders/orders"
            timestamp = int(time.time())
            
            # Create order payload with exit plan
            payload = {
                "idempotency_key": f"test_ws_exit_{strategy_id}_{timestamp}",
                "environment": {
                    "sandbox": True
                },
                "source": {
                    "strategy_id": strategy_id,
                    "instance_id": "ws_test",
                    "owner": "test_user"
                },
                "order": {
                    "instrument": {
                        "class": "crypto_perp",
                        "symbol": symbol
                    },
                    "side": "BUY",
                    "quantity": {
                        "type": "contracts",
                        "value": 0.001
                    },
                    "order_type": "MARKET",
                    "time_in_force": "IOC",
                    "flags": {
                        "post_only": False,
                        "reduce_only": False,
                        "hidden": False,
                        "iceberg": {},
                        "allow_partial_fills": True
                    },
                    "routing": {
                        "mode": "AUTO"
                    },
                    "leverage": {
                        "enabled": False
                    },
                    "exit_plan": {
                        "legs": [
                            {
                                "kind": "TP",
                                "label": "Quick TP (50%)",
                                "allocation": {
                                    "type": "percentage",
                                    "value": 50.0
                                },
                                "trigger": {
                                    "mode": "PRICE",
                                    "price_type": "MARK",
                                    "value": 50050.0  # Very close to entry for quick trigger
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
                                "kind": "SL",
                                "label": "Stop Loss",
                                "allocation": {
                                    "type": "percentage",
                                    "value": 100.0
                                },
                                "trigger": {
                                    "mode": "PRICE",
                                    "price_type": "MARK",
                                    "value": 49950.0  # Very close to entry for quick trigger
                                },
                                "exec": {
                                    "order_type": "MARKET",
                                    "time_in_force": "GTC"
                                }
                            }
                        ]
                    }
                }
            }
            
            body = json.dumps(payload)
            signature = self.create_hmac_signature(timestamp, method, path, body)
            
            headers = {
                "Authorization": f'HMAC key_id="{self.api_key}", signature="{signature}", ts={timestamp}',
                "Content-Type": "application/json"
            }
            
            url = f"{self.base_url}{path}"
            
            logger.info(f"📤 Creating test order with exit plan for strategy: {strategy_id}")
            logger.info(f"📋 Order details: {symbol} BUY 0.001 @ MARKET with TP/SL")
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, headers=headers) as response:
                    result = await response.json()
                    
                    if response.status == 200:
                        logger.info(f"✅ Order with exit plan created: {result.get('order_ref')}")
                        return result
                    else:
                        logger.error(f"❌ Order creation failed: {response.status} - {result}")
                        return {"error": result}
                        
        except Exception as e:
            logger.error(f"❌ Error creating test order with exit plan: {e}")
            return {"error": str(e)}
    
    async def get_positions(self, strategy_id: str) -> Dict[str, Any]:
        """Get positions for a strategy"""
        try:
            method = "GET"
            path = f"/api/v1/positions?strategy_id={strategy_id}"
            timestamp = int(time.time())
            body = ""
            signature = self.create_hmac_signature(timestamp, method, path, body)
            
            headers = {
                "Authorization": f'HMAC key_id="{self.api_key}", signature="{signature}", ts={timestamp}',
                "Content-Type": "application/json"
            }
            
            url = f"{self.base_url}{path}"
            
            logger.info(f"📤 Getting positions for strategy: {strategy_id}")
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers) as response:
                    result = await response.json()
                    
                    if response.status == 200:
                        positions = result.get("positions", [])
                        logger.info(f"✅ Found {len(positions)} positions for {strategy_id}")
                        for pos in positions:
                            logger.info(f"   Position: {pos.get('position_ref')} - {pos.get('symbol')} - {pos.get('state')}")
                        return result
                    else:
                        logger.error(f"❌ Failed to get positions: {response.status} - {result}")
                        return {"error": result}
                        
        except Exception as e:
            logger.error(f"❌ Error getting positions: {e}")
            return {"error": str(e)}

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

async def main():
    """Main test function"""
    print("🧪 WebSocket Event Trigger Test")
    print("=" * 50)
    
    # Load API keys
    api_key, secret_key = load_api_keys()
    if not api_key or not secret_key:
        return
    
    # Create event trigger
    trigger = EventTrigger(api_key, secret_key)
    
    # Get strategy ID from user
    strategy_id = input("Enter strategy ID to test (or press Enter for 'test_strategy'): ").strip()
    if not strategy_id:
        strategy_id = "test_strategy"
    
    print(f"\n🚀 Testing events for strategy: {strategy_id}")
    
    # Test 1: Create simple order
    print("\n📋 Test 1: Creating simple market order...")
    result1 = await trigger.create_test_order(strategy_id)
    
    # Wait a bit
    await asyncio.sleep(2)
    
    # Test 2: Create order with exit plan
    print("\n📋 Test 2: Creating order with exit plan...")
    result2 = await trigger.create_test_order_with_exit_plan(strategy_id)
    
    # Wait a bit
    await asyncio.sleep(2)
    
    # Test 3: Get positions
    print("\n📊 Test 3: Getting positions...")
    positions = await trigger.get_positions(strategy_id)
    
    print(f"\n✅ Event triggering complete!")
    print(f"💡 Check your WebSocket monitor to see the events in real-time")
    print(f"🔍 Events should include:")
    print(f"   - ORDER_UPDATE events for both orders")
    print(f"   - FILL events when orders execute")
    print(f"   - POSITION_UPDATE events for position changes")
    print(f"   - STOP_TRIGGERED/TAKE_PROFIT_TRIGGERED events from exit plan")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 Test stopped by user")
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
