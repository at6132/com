#!/usr/bin/env python3
"""
Debug script to see exactly what the exit plan looks like
"""
import asyncio
import json
import time
import aiohttp
import hmac
import hashlib
from datetime import datetime

# Configuration
COM_BASE_URL = "http://localhost:8000"

class ExitPlanDebugger:
    def __init__(self):
        self.api_key = None
        self.secret_key = None

    def create_signature(self, timestamp, method, endpoint, body=""):
        """Create HMAC signature for authentication"""
        message = f"{timestamp}{method}{endpoint}{body}"
        signature = hmac.new(
            self.secret_key.encode('utf-8'),
            message.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        return signature

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
                    print("❌ No active API key found")
                    return False

        except Exception as e:
            print(f"❌ Error loading API keys: {e}")
            return False

    async def send_debug_request(self):
        """Send a request with debug logging enabled"""
        print("=== Sending Debug Exit Plan Request ===")

        # Load real API keys first
        if not await self.load_api_keys():
            return

        # Simple exit plan for testing
        order_payload = {
            "idempotency_key": f"debug_exit_plan_{int(time.time())}",
            "environment": {
                "sandbox": True
            },
            "source": {
                "strategy_id": "debug_strategy",
                "instance_id": "debug_instance",
                "owner": "debug_owner"
            },
            "order": {
                "instrument": {
                    "class": "crypto_perp",
                    "symbol": "DOGE_USDT"
                },
                "side": "BUY",
                "quantity": {
                    "type": "contracts",
                    "value": 10
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
                    "enabled": True,
                    "leverage": 25
                },
                "exit_plan": {
                    "legs": [
                        {
                            "kind": "TP",
                            "trigger": {
                                "mode": "PRICE",
                                "price_type": "MARK",
                                "value": 0.2105  # Fixed TP price for testing
                            },
                            "allocation": {
                                "type": "percentage",
                                "value": 100.0
                            },
                            "exec": {
                                "type": "MARKET",
                                "post_only": False,
                                "time_in_force": "IOC"
                            }
                        },
                        {
                            "kind": "SL",
                            "trigger": {
                                "mode": "PRICE",
                                "price_type": "MARK",
                                "value": 0.2101  # Fixed SL price for testing
                            },
                            "allocation": {
                                "type": "percentage",
                                "value": 100.0
                            },
                            "exec": {
                                "type": "MARKET",
                                "post_only": False,
                                "time_in_force": "GTC"
                            }
                        }
                    ]
                }
            }
        }

        # Create signature
        timestamp = str(int(time.time() * 1000))
        endpoint = "/api/v1/orders/orders"
        method = "POST"
        body = json.dumps(order_payload, separators=(',', ':'))
        signature = self.create_signature(timestamp, method, endpoint, body)

        headers = {
            'Content-Type': 'application/json',
            'X-API-Key': self.api_key,
            'X-Timestamp': timestamp,
            'X-Signature': signature
        }

        try:
            async with aiohttp.ClientSession() as session:
                url = f"{COM_BASE_URL}{endpoint}"
                print(f"Sending request to: {url}")
                print(f"Payload: {json.dumps(order_payload, indent=2)}")

                async with session.post(url, headers=headers, data=body) as response:
                    print(f"Response status: {response.status}")
                    response_text = await response.text()
                    print(f"Response: {response_text}")

                    if response.status == 200:
                        print("✅ Request successful!")
                    else:
                        print(f"❌ Request failed with status {response.status}")

        except Exception as e:
            print(f"❌ Error sending request: {e}")

if __name__ == "__main__":
    debugger = ExitPlanDebugger()

    print("🚀 Starting Exit Plan Debug Test")
    print("Make sure COM server is running on localhost:8000")
    print("This will show exactly what the exit plan looks like when processed")

    asyncio.run(debugger.send_debug_request())
