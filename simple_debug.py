#!/usr/bin/env python3
"""
Simple debug script to test exit plan processing directly
"""
import sys
import os

# Add com directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'com'))

from app.services.order_monitor import order_monitor

# Test exit plan structure
test_exit_plan = {
    "legs": [
        {
            "kind": "TP",
            "trigger": {
                "mode": "PRICE",
                "price_type": "MARK",
                "value": 0.2105
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
                "value": 0.2101
            },
            "exec": {
                "type": "MARKET",
                "post_only": False,
                "time_in_force": "GTC"
            }
        }
    ]
}

print("=== Testing Exit Plan Processing ===")
print(f"Exit plan: {test_exit_plan}")

# Test the leg processing logic
legs = test_exit_plan["legs"]
tp_leg = None
sl_leg = None
tp_post_only = False
sl_post_only = False

for leg in legs:
    print(f"🔧 Processing leg: {leg}, type: {type(leg)}")

    # This is the logic from order_monitor.py
    leg_kind = leg.get('kind')
    print(f"🔧 Leg kind (dict): {leg_kind}")

    exec_config = leg.get('exec', {})
    print(f"🔧 Exec config (dict): {exec_config}")

    post_only_value = exec_config.get('post_only', False) if isinstance(exec_config, dict) else False
    print(f"🔧 Post-only value (dict): {post_only_value}")

    if post_only_value:
        if leg_kind == 'TP':
            tp_post_only = True
            print("🔧 Set TP as post-only")
        elif leg_kind == 'SL':
            sl_post_only = True
            print("🔧 Set SL as post-only")
    if leg_kind == 'TP':
        tp_leg = leg
    elif leg_kind == 'SL':
        sl_leg = leg

print("\n=== Results ===")
print(f"TP Leg: {tp_leg}")
print(f"SL Leg: {sl_leg}")
print(f"TP Post-only: {tp_post_only}")
print(f"SL Post-only: {sl_post_only}")

# Test price extraction
if tp_leg:
    print("\n=== TP Price Extraction ===")
    if hasattr(tp_leg, 'trigger'):
        print(f"TP trigger object: {tp_leg.trigger}")
        if hasattr(tp_leg.trigger, 'value'):
            tp_price = tp_leg.trigger.value
            print(f"TP price extracted via trigger.value: {tp_price}")
        elif hasattr(tp_leg.trigger, 'get'):
            tp_price = tp_leg.trigger.get('value')
            print(f"TP price extracted via trigger.get('value'): {tp_price}")
    else:
        # Dict format
        tp_price = tp_leg.get('trigger', {}).get('value')
        print(f"TP price extracted via dict fallback: {tp_price}")

if sl_leg:
    print("\n=== SL Price Extraction ===")
    print(f"SL leg attributes: {dir(sl_leg)}")
    print(f"SL leg has 'trigger' attr: {hasattr(sl_leg, 'trigger')}")
    print(f"SL leg type: {type(sl_leg)}")

    if hasattr(sl_leg, 'trigger'):
        print(f"SL trigger object: {sl_leg.trigger}")
        if hasattr(sl_leg.trigger, 'value'):
            sl_price = sl_leg.trigger.value
            print(f"SL price extracted via trigger.value: {sl_price}")
        elif hasattr(sl_leg.trigger, 'get'):
            sl_price = sl_leg.trigger.get('value')
            print(f"SL price extracted via trigger.get('value'): {sl_price}")
        else:
            print("SL trigger has neither 'value' nor 'get' attribute")
    else:
        # Dict format
        sl_price = sl_leg.get('trigger', {}).get('value')
        print(f"SL price extracted via dict fallback: {sl_price}")
        print(f"SL leg dict keys: {sl_leg.keys() if hasattr(sl_leg, 'keys') else 'no keys method'}")

print("\n=== Summary ===")
print("If prices are None, the extraction logic needs to be fixed!")
print("If post_only values are False, then trigger orders should be placed!")
