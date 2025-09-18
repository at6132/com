#!/usr/bin/env python3
"""
Simple test script for sending orders with exit plans
"""
import asyncio
import json
import time
import aiohttp
import hmac
import hashlib
from datetime import datetime
from typing import Dict, Any

# Configuration
COM_BASE_URL = "http://localhost:8000"
MEXC_API_URL = "https://api.mexc.com"

class ExitPlanTester:
    def __init__(self):
        self.order_id = None
        self.api_key = None
        self.secret_key = None
        
    async def load_api_keys(self):
        """Load API keys from the database"""
        print("=== Loading API Keys from Database ===")
        
        try:
            # Add the com directory to the path
            import sys
            import os
            sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'com'))
            
            from app.core.database import get_async_session_local
            from app.core.database import ApiKey
            from sqlalchemy import select
            
            session_maker = get_async_session_local()
            async with session_maker() as db:
                # Get the first active API key
                result = await db.execute(
                    select(ApiKey).where(ApiKey.is_active == True).limit(1)
                )
                api_key = result.scalar_one_or_none()
                
                if api_key and api_key.secret_key:
                    self.api_key = api_key.key_id
                    self.secret_key = api_key.secret_key
                    print(f"✅ Loaded API key: {self.api_key[:20]}...")
                    print(f"✅ Secret key: {self.secret_key[:10]}...")
                    return True
                else:
                    print("❌ No active API key with secret found in database")
                    return False
                    
        except Exception as e:
            print(f"❌ Error loading API keys: {e}")
            import traceback
            traceback.print_exc()
            return False
        
    def create_hmac_signature(self, timestamp: int, method: str, path: str, body: str) -> str:
        """Create HMAC signature for REST API authentication"""
        # Server expects: timestamp\nmethod\npath\nbody
        base_string = f"{timestamp}\n{method}\n{path}\n{body}"
        signature = hmac.new(
            self.secret_key.encode('utf-8'),
            base_string.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        return signature
    

    
    async def send_order_with_exit_plan(self):
        """Send an order with an advanced exit plan to COM"""
        print("=== Sending Order with Exit Plan ===")
        
        # Get current BTC price to set realistic TP/SL levels
        async with aiohttp.ClientSession() as session:
            try:
                response = await session.get(f"{MEXC_API_URL}/api/v3/ticker/price?symbol=DOGEUSDT")
                if response.status == 200:
                    data = await response.json()
                    current_price = float(data['price'])
                    print(f"Current BTC price: ${current_price:,.2f}")
                    
                    # Set much closer levels for testing
                    self.entry_price = current_price
                    self.tp1_price = current_price * 0.9990  # -0.10%
                    self.tp2_price = current_price * 0.9985  # -0.15%
                    self.sl1_price = current_price * 1.0005  # +0.05%
                    
                    print(f"Entry price: ${self.entry_price:,.5f}")
                    print(f"TP1 (60%): ${self.tp1_price:,.5f} (-0.05%)")
                    print(f"TP2 (40%): ${self.tp2_price:,.5f} (-0.10%)")
                    print(f"SL1: ${self.sl1_price:,.5f} (+0.05%)")
                else:
                    print(f"Failed to get current price: {response.status}")
                    return False
            except Exception as e:
                print(f"Error getting current price: {e}")
                return False
        
        # Create order payload with correct COM server schema
        order_payload = {
            "idempotency_key": f"test_exit_plan_001_BTCUSDT_{int(time.time())}",
            "environment": {
                "sandbox": True
            },
            "source": {
                "strategy_id": "test_exit_plan_001",
                "instance_id": "test_instance_001",
                "owner": "test_owner"
            },
            "order": {
                "instrument": {
                    "class": "crypto_perp",
                    "symbol": "DOGE_USDT"
                },
                "side": "SELL",
                "quantity": {
                    "type": "contracts",
                    "value": 100
                },
                "order_type": "MARKET",
                # No price for MARKET orders - they execute at current market price
                "time_in_force": "IOC",  # IOC for MARKET orders
                "flags": {
                    "post_only": False,  # MARKET orders can't be post-only
                    "reduce_only": False,
                    "hidden": False,
                    "iceberg": {},
                    "allow_partial_fills": True
                },
                "routing": {
                    "mode": "AUTO"
                },
                "leverage": {
                    "enabled": True,
                    "leverage": 25
                },
                "exit_plan": {
                    "legs": [
                        {
                            "kind": "TP",
                            "label": "TP1 (60% Scale-out)",
                            "allocation": {
                                "type": "percentage",
                                "value": 60.0
                            },
                            "trigger": {
                                "mode": "PRICE",
                                "price_type": "MARK",
                                "value": self.tp1_price
                            },
                            "exec": {
                                "order_type": "LIMIT",
                                "price": self.tp1_price,
                                "time_in_force": "GTC",
                                "flags": {
                                    "post_only": True,
                                    "reduce_only": True,
                                    "hidden": False,
                                    "iceberg": {},
                                    "allow_partial_fills": True
                                }
                            },
                            "after_fill_actions": [
                                {
                                    "action": "SET_SL_TO_BREAKEVEN"
                                }
                            ]
                        },
                        {
                            "kind": "TP",
                            "label": "TP2 (40% Runner)",
                            "allocation": {
                                "type": "percentage",
                                "value": 40.0
                            },
                            "trigger": {
                                "mode": "PRICE",
                                "price_type": "MARK",
                                "value": self.tp2_price
                            },
                            "exec": {
                                "order_type": "LIMIT",
                                "price": self.tp2_price,
                                "time_in_force": "GTC",
                                "flags": {
                                    "post_only": True,
                                    "reduce_only": True,
                                    "hidden": False,
                                    "iceberg": {},
                                    "allow_partial_fills": True
                                }
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
                                "value": self.sl1_price
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
        
        print(f"Order payload: {json.dumps(order_payload, indent=2)}")
        
        # Generate HMAC signature for REST API
        timestamp = int(time.time())  # Use seconds, not milliseconds for REST API
        method = "POST"
        path = "/api/v1/orders/orders"
        body = json.dumps(order_payload)
        
        signature = self.create_hmac_signature(timestamp, method, path, body)
        
        headers = {
            "Authorization": f"HMAC key_id=\"{self.api_key}\", signature=\"{signature}\", ts={timestamp}",
            "Content-Type": "application/json"
        }
        
        # Send order
        try:
            async with aiohttp.ClientSession() as session:
                response = await session.post(
                    f"{COM_BASE_URL}/api/v1/orders/orders",
                    json=order_payload,
                    headers=headers
                )
                
                if response.status == 200:
                    result = await response.json()
                    # Check if it's an Ack response (success) or ErrorEnvelope
                    if result.get('status') == 'ACK':
                        self.order_id = result.get('order_ref')
                        print(f"✅ Order sent successfully: {self.order_id}")
                        print(f"Response: {json.dumps(result, indent=2)}")
                        return True
                    else:
                        print(f"❌ Order creation failed: {result}")
                        return False
                else:
                    error_text = await response.text()
                    print(f"❌ Failed to send order: {response.status}")
                    print(f"Error: {error_text}")
                    return False
                    
        except Exception as e:
            print(f"❌ Error sending order: {e}")
            return False
    

    
    async def run_test(self):
        """Run the order sending test"""
        print("🚀 Starting Exit Plan Order Test")
        print("=" * 50)
        print("📋 Test Strategy:")
        print("   1. Fetch current DOGE price")
        print("   2. Send MARKET entry order with complex exit plan")
        print("   3. TP1: 60% scale-out at -0.05% (post-only LIMIT)")
        print("   4. TP2: 40% runner at -0.10% (post-only LIMIT)")
        print("   5. SL1: Stop loss at +0.05% (MARKET)")
        print("=" * 50)
        
        try:
            # Step 1: Load API keys
            if not await self.load_api_keys():
                print("❌ Failed to load API keys, aborting test")
                return
            
            print("\n" + "=" * 50)
            
            # Step 2: Send order with exit plan
            if not await self.send_order_with_exit_plan():
                print("❌ Failed to send order, aborting test")
                return
            
            print("\n" + "=" * 50)
            print("=== Test Results ===")
            print(f"✅ Order sent successfully: {self.order_id}")
            print(f"🎯 TP1 (60%): ${self.tp1_price:,.5f} (-0.05%)")
            print(f"🎯 TP2 (40%): ${self.tp2_price:,.5f} (-0.10%)")
            print(f"🛑 SL1: ${self.sl1_price:,.5f} (+0.05%)")
            print("\n✅ Complex exit plan test completed!")
            
        except KeyboardInterrupt:
            print("\n\n⏹️ Test interrupted by user")
        except Exception as e:
            print(f"\n❌ Test failed with error: {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    tester = ExitPlanTester()
    asyncio.run(tester.run_test())
