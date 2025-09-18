#!/usr/bin/env python3
"""
Test script for order logging with TP/SL
"""

import asyncio
import json
import time
from datetime import datetime
import requests

async def test_order_logging():
    """Test order logging with TP/SL exit plan"""
    
    # COM API endpoint
    base_url = "http://localhost:8000"
    
    # Test order with TP/SL
    order_data = {
        "idempotency_key": f"test_order_{int(time.time())}",
        "environment": "paper",
        "order": {
            "instrument": {
                "class": "crypto_perp",
                "symbol": "BTCUSDT"
            },
            "side": "BUY",
            "quantity": {
                "type": "contracts",
                "value": 0.001
            },
            "order_type": "MARKET",
            "time_in_force": "IOC",
            "leverage": {
                "leverage": 1.0
            },
            "exit_plan": {
                "legs": [
                    {
                        "kind": "TP",
                        "allocation": {
                            "type": "percentage",
                            "value": 100.0
                        },
                        "trigger": {
                            "type": "price",
                            "value": 45000.0
                        },
                        "exec": {
                            "post_only": True
                        }
                    },
                    {
                        "kind": "SL",
                        "allocation": {
                            "type": "percentage",
                            "value": 100.0
                        },
                        "trigger": {
                            "type": "price",
                            "value": 44000.0
                        },
                        "exec": {
                            "post_only": True
                        }
                    }
                ]
            }
        },
        "source": {
            "strategy_id": "test_strategy_001",
            "instance_id": "test_account_001"
        }
    }
    
    try:
        print("🚀 Sending test order with TP/SL...")
        print(f"📊 Order data: {json.dumps(order_data, indent=2)}")
        
        # Send order to COM
        response = requests.post(
            f"{base_url}/api/v1/orders",
            json=order_data,
            headers={"Content-Type": "application/json"}
        )
        
        if response.status_code == 200:
            result = response.json()
            print("✅ Order sent successfully!")
            print(f"📋 Order result: {json.dumps(result, indent=2)}")
            
            # Wait a moment for processing
            await asyncio.sleep(2)
            
            # Check if orders were logged
            print("\n📊 Checking order logs...")
            try:
                with open("data/logs/orders/main_orders.csv", "r") as f:
                    lines = f.readlines()
                    print(f"📄 Found {len(lines)} lines in main_orders.csv")
                    
                    if len(lines) > 1:  # Header + at least one order
                        print("📋 Recent orders:")
                        for i, line in enumerate(lines[-3:], 1):  # Last 3 lines
                            print(f"  {i}. {line.strip()}")
                    else:
                        print("⚠️  No orders found in CSV")
                        
            except FileNotFoundError:
                print("⚠️  main_orders.csv not found")
            except Exception as e:
                print(f"❌ Error reading CSV: {e}")
                
        else:
            print(f"❌ Failed to send order: {response.status_code}")
            print(f"Error: {response.text}")
            
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_order_logging())
