#!/usr/bin/env python3
"""
Test script to verify order monitoring system is working
"""
import asyncio
import aiohttp
import json
import time
import hmac
import hashlib
import base64

# Load API keys
with open("keys/GUI_20250831_180858_keys.json", "r") as f:
    keys = json.load(f)

API_KEY = keys["api_key"]
SECRET_KEY = keys["secret_key"]

def create_hmac_signature(method: str, path: str, body: str, timestamp: int) -> str:
    """Create HMAC signature for API authentication"""
    message = f"{method}{path}{body}{timestamp}"
    signature = hmac.new(
        SECRET_KEY.encode('utf-8'),
        message.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()
    return signature

async def send_test_order():
    """Send a test order with exit plan to verify monitoring"""
    
    # Get current BTC price for realistic TP/SL levels
    async with aiohttp.ClientSession() as session:
        async with session.get("https://contract.mexc.com/api/v1/contract/ticker?symbol=BTC_USDT") as response:
            if response.status == 200:
                data = await response.json()
                current_price = float(data['data']['last'])
                print(f"Current BTC price: ${current_price:,.2f}")
                
                # Set TP at 0.1% above, SL at 0.1% below (tight for testing)
                tp_price = current_price * 1.001
                sl_price = current_price * 0.999
                
                print(f"TP will be set at: ${tp_price:,.2f} (+0.1%)")
                print(f"SL will be set at: ${sl_price:,.2f} (-0.1%)")
            else:
                print("Failed to get current price, using default values")
                current_price = 109000
                tp_price = 109109
                sl_price = 108891
    
    # Create order payload
    order_payload = {
        "idempotency_key": f"test_monitoring_{int(time.time())}",
        "environment": {
            "sandbox": True
        },
        "source": {
            "strategy_id": "test_monitoring",
            "instance_id": "test_instance",
            "owner": "test_owner"
        },
        "order": {
            "instrument": {
                "class": "crypto_perp",
                "symbol": "BTC_USDT"
            },
            "side": "BUY",
            "quantity": {
                "type": "contracts",
                "value": 0.0001  # Small amount for testing
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
                "broker": "mexc",
                "venue": "mexc_futures"
            },
            "leverage": {
                "enabled": True,
                "leverage": 10.0
            },
            "exit_plan": {
                "legs": [
                    {
                        "kind": "TP",
                        "trigger": {
                            "mode": "PRICE",
                            "price_type": "MARK",
                            "value": tp_price
                        },
                        "allocation": {
                            "type": "percentage",
                            "value": 100.0
                        },
                        "exec": {
                            "type": "LIMIT",
                            "post_only": True,
                            "time_in_force": "GTC"
                        }
                    },
                    {
                        "kind": "SL",
                        "trigger": {
                            "mode": "PRICE",
                            "price_type": "MARK",
                            "value": sl_price
                        },
                        "allocation": {
                            "type": "percentage",
                            "value": 100.0
                        },
                        "exec": {
                            "type": "LIMIT",
                            "post_only": True,
                            "time_in_force": "GTC"
                        }
                    }
                ]
            }
        }
    }
    
    # Create HMAC signature
    timestamp = int(time.time())
    body = json.dumps(order_payload)
    signature = create_hmac_signature("POST", "/api/v1/orders/orders", body, timestamp)
    
    headers = {
        "Content-Type": "application/json",
        "X-API-Key": API_KEY,
        "X-Timestamp": str(timestamp),
        "X-Signature": signature
    }
    
    print(f"\n🚀 Sending test order with monitoring...")
    print(f"Order payload: {json.dumps(order_payload, indent=2)}")
    
    # Send order
    async with aiohttp.ClientSession() as session:
        async with session.post(
            "http://localhost:8000/api/v1/orders/orders",
            headers=headers,
            data=body
        ) as response:
            result = await response.json()
            print(f"\n📊 Order response: {json.dumps(result, indent=2)}")
            
            if response.status == 200:
                print("✅ Order sent successfully!")
                return True
            else:
                print(f"❌ Order failed: {response.status}")
                return False

async def check_monitoring_status():
    """Check if order is being monitored"""
    print(f"\n🔍 Checking monitoring status...")
    
    async with aiohttp.ClientSession() as session:
        async with session.get("http://localhost:8000/api/v1/orders/monitoring/status") as response:
            if response.status == 200:
                result = await response.json()
                print(f"Monitoring status: {json.dumps(result, indent=2)}")
                return result
            else:
                print(f"❌ Failed to get monitoring status: {response.status}")
                return None

async def main():
    """Main test function"""
    print("🧪 Testing Order Monitoring System")
    print("=" * 50)
    
    # Check initial monitoring status
    await check_monitoring_status()
    
    # Send test order
    success = await send_test_order()
    
    if success:
        # Wait a moment for order to be processed
        print("\n⏳ Waiting for order to be processed...")
        await asyncio.sleep(3)
        
        # Check monitoring status again
        await check_monitoring_status()
        
        print("\n✅ Test completed! Check the logs to see if monitoring is working.")
        print("💡 The order should now be monitored for TP/SL triggers.")
    else:
        print("\n❌ Test failed - order was not sent successfully")

if __name__ == "__main__":
    asyncio.run(main())
