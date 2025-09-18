#!/usr/bin/env python3
"""
Monitor MEXC for TP/SL executions to understand the data structure
"""

import asyncio
import json
import sys
import os
from pathlib import Path
from datetime import datetime

# Add the mexc_python directory to Python path
mexc_path = Path(__file__).parent / "mexc_python"
if mexc_path.exists():
    sys.path.insert(0, str(mexc_path))

try:
    from mexcpy.api import MexcFuturesAPI
    MEXC_AVAILABLE = True
    print(f"✅ MEXC Python SDK loaded from: {mexc_path}")
except ImportError as e:
    MEXC_AVAILABLE = False
    print(f"❌ MEXC Python SDK not available: {e}")
    exit(1)

async def monitor_tp_sl_executions():
    print("🔍 Monitoring MEXC for TP/SL Executions")
    print("=" * 60)
    
    # Load MEXC token from config
    print("📋 Loading MEXC token from config...")
    try:
        # Add the com directory to the path
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'com'))
        
        from app.config.brokers import broker_registry
        
        enabled_brokers = broker_registry.get_enabled_brokers()
        mexc_config = enabled_brokers.get("mexc", {})
        
        if not mexc_config or not mexc_config.token:
            print("❌ No MEXC token found in config")
            return
        
        token = mexc_config.token
        testnet = mexc_config.testnet
        print(f"✅ Loaded MEXC token: {token[:20]}...")
        print(f"✅ Testnet mode: {testnet}")
        
    except Exception as e:
        print(f"❌ Error loading MEXC config: {e}")
        return
    
    # Initialize MEXC API
    print("\n📋 Initializing MEXC API...")
    try:
        api = MexcFuturesAPI(
            token=token,
            testnet=testnet
        )
        print("✅ MEXC API initialized with token")
                
    except Exception as e:
        print(f"❌ Error initializing MEXC API: {e}")
        return
    
    try:
        print("\n🔍 Looking for TP/SL related data...")
        print("-" * 40)
        
        # 1. Check for recent transactions with side=4 (CLOSE)
        print("📊 1. Checking for CLOSE transactions (side=4)...")
        trades_result = await api.get_order_transactions_by_symbol(symbol="DOGE_USDT", page_size=20)
        
        if trades_result.success and trades_result.data:
            close_transactions = [t for t in trades_result.data if t.get('side') == 4]
            print(f"✅ Found {len(close_transactions)} CLOSE transactions")
            
            for i, transaction in enumerate(close_transactions[:3]):
                print(f"\n🔍 CLOSE Transaction {i+1}:")
                print(json.dumps(transaction, indent=2, default=str))
                print("-" * 30)
                
            # Test get_order_by_order_id with the most recent CLOSE transaction
            if close_transactions:
                most_recent_close = close_transactions[0]  # First one is most recent
                order_id = most_recent_close.get('orderId')
                
                print(f"\n🔍 Testing get_order_by_order_id with most recent CLOSE transaction...")
                print(f"Order ID: {order_id}")
                
                try:
                    order_details_result = await api.get_order_by_order_id(order_id)
                    if order_details_result.success and order_details_result.data:
                        print("✅ Order details retrieved successfully:")
                        order_details = order_details_result.data
                        print(json.dumps(order_details, indent=2, default=str))
                        
                        # Extract key information
                        if hasattr(order_details, 'triggerType'):
                            trigger_type = order_details.triggerType
                            trigger_name = {1: "TAKE_PROFIT", 2: "STOP_LOSS"}.get(trigger_type, f"UNKNOWN({trigger_type})")
                            print(f"\n💡 This was a {trigger_name} execution!")
                        
                        if hasattr(order_details, 'state'):
                            state = order_details.state
                            state_name = {1: "PENDING", 2: "ACTIVE", 3: "FILLED", 4: "CANCELLED"}.get(state, f"UNKNOWN({state})")
                            print(f"💡 Order state: {state_name} ({state})")
                            
                    else:
                        print("❌ Failed to get order details")
                        print(f"Raw response: {order_details_result}")
                        
                except Exception as e:
                    print(f"❌ Error getting order details: {e}")
                    import traceback
                    print(f"Traceback: {traceback.format_exc()}")
        else:
            print("❌ No transactions found")
        
        # 2. Check trigger orders for TP/SL
        print("\n📊 2. Checking trigger orders for TP/SL...")
        trigger_result = await api.get_trigger_orders(symbol="DOGE_USDT", page_size=20)
        
        if trigger_result.success and trigger_result.data:
            tp_sl_triggers = [t for t in trigger_result.data if t.get('triggerType') in [1, 2]]
            print(f"✅ Found {len(tp_sl_triggers)} TP/SL trigger orders")
            
            for i, trigger in enumerate(tp_sl_triggers[:5]):
                trigger_type = "TAKE_PROFIT" if trigger.get('triggerType') == 1 else "STOP_LOSS"
                state = trigger.get('state')
                state_name = {1: "PENDING", 2: "ACTIVE", 3: "FILLED", 4: "CANCELLED"}.get(state, f"UNKNOWN({state})")
                
                print(f"\n🔍 {trigger_type} Trigger {i+1} (State: {state_name}):")
                print(f"  ID: {trigger.get('id')}")
                print(f"  Trigger Price: {trigger.get('triggerPrice')}")
                print(f"  Order Price: {trigger.get('price')}")
                print(f"  Volume: {trigger.get('vol')}")
                print(f"  Create Time: {datetime.fromtimestamp(trigger.get('createTime', 0)/1000)}")
                print(f"  Update Time: {datetime.fromtimestamp(trigger.get('updateTime', 0)/1000)}")
                print("-" * 30)
        else:
            print("❌ No trigger orders found")
        
        # 3. Check historical orders for any with TP/SL prices
        print("\n📊 3. Checking historical orders for TP/SL info...")
        orders_result = await api.get_historical_orders(symbol="DOGE_USDT", page_size=10)
        
        if orders_result.success and orders_result.data:
            print(f"✅ Found {len(orders_result.data)} historical orders")
            
            for i, order in enumerate(orders_result.data[:3]):
                order_id = order.get('orderId')
                side = order.get('side')
                side_name = {1: "BUY", 2: "SELL", 3: "BUY", 4: "CLOSE"}.get(side, f"UNKNOWN({side})")
                state = order.get('state')
                state_name = {1: "PENDING", 2: "PARTIAL", 3: "FILLED", 4: "CANCELLED"}.get(state, f"UNKNOWN({state})")
                
                print(f"\n🔍 Order {i+1}:")
                print(f"  ID: {order_id}")
                print(f"  Side: {side_name} ({side})")
                print(f"  State: {state_name} ({state})")
                print(f"  Price: {order.get('price')}")
                print(f"  Volume: {order.get('vol')}")
                print(f"  Deal Volume: {order.get('dealVol')}")
                print(f"  Create Time: {datetime.fromtimestamp(order.get('createTime', 0)/1000)}")
                print(f"  Update Time: {datetime.fromtimestamp(order.get('updateTime', 0)/1000)}")
                print("-" * 30)
        else:
            print("❌ No historical orders found")
        
        print("\n" + "=" * 60)
        print("✅ TP/SL Monitoring Complete!")
        print("\n💡 Key Insights:")
        print("- Look for transactions with side=4 (CLOSE) to detect TP/SL executions")
        print("- Check trigger orders with triggerType=1 (TP) or triggerType=2 (SL)")
        print("- Monitor trigger order state changes from ACTIVE(2) to FILLED(3)")
        print("- Use orderId to link transactions to their parent orders")
        
    except Exception as e:
        print(f"❌ Error monitoring MEXC: {e}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")

if __name__ == "__main__":
    asyncio.run(monitor_tp_sl_executions())

