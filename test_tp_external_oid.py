#!/usr/bin/env python3
"""
Test script to check what externalOid values TP orders have
"""
import asyncio
import sys
import os

# Add the com directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'com'))

from app.adapters.manager import broker_manager

async def check_tp_external_oid():
    """Check what externalOid values TP orders have"""
    print("=== Checking TP Order ExternalOid Values ===")
    
    try:
        # Get broker adapter
        broker_name = "mexc"
        await broker_manager.ensure_broker_connected(broker_name)
        broker = broker_manager.get_adapter(broker_name)
        
        if not broker:
            print("❌ MEXC broker adapter not found")
            return
        
        # Get recent trades to see what externalOid values look like
        print("🔍 Getting recent trades...")
        trades = await broker.get_recent_trades(symbol="DOGE_USDT", limit=10)
        
        if trades:
            print(f"📊 Found {len(trades)} recent trades")
            for i, trade in enumerate(trades):
                print(f"Trade {i+1}: {trade}")
                
                # Get order details to check externalOid
                order_id = trade.get('order_id')
                if order_id:
                    print(f"🔍 Getting order details for {order_id}...")
                    order_details = await broker.get_order(order_id)
                    if order_details:
                        # Handle both dict and object responses
                        if hasattr(order_details, 'externalOid'):
                            external_oid = getattr(order_details, 'externalOid', '')
                        else:
                            external_oid = order_details.get('externalOid', '')
                        
                        print(f"📋 Order {order_id} externalOid: '{external_oid}'")
                        
                        # Check if it matches our patterns
                        if 'stoporder_TAKE_PROFIT_' in external_oid:
                            print(f"✅ Matches TAKE_PROFIT pattern")
                        elif 'stoporder_STOP_LOSS_' in external_oid:
                            print(f"✅ Matches STOP_LOSS pattern")
                        else:
                            print(f"❌ No pattern match")
                    else:
                        print(f"❌ Could not get order details for {order_id}")
        else:
            print("❌ No recent trades found")
            
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(check_tp_external_oid())
