#!/usr/bin/env python3
"""
Simple script to view error logs from errors.csv
"""
import csv
import json
from pathlib import Path
from datetime import datetime

def view_errors(limit: int = 10):
    """View recent errors from errors.csv"""
    errors_file = Path("Logs/errors.csv")
    
    if not errors_file.exists():
        print("❌ No errors.csv file found in Logs/ directory")
        return
    
    print(f"📋 Recent Errors (last {limit}):")
    print("=" * 80)
    
    with open(errors_file, 'r') as f:
        reader = csv.DictReader(f)
        errors = list(reader)
    
    # Show most recent errors first
    recent_errors = errors[-limit:] if len(errors) > limit else errors
    
    for i, error in enumerate(reversed(recent_errors), 1):
        print(f"\n🔴 Error #{i}:")
        print(f"   Time: {error['timestamp']}")
        print(f"   Type: {error['error_type']}")
        print(f"   Message: {error['error_message']}")
        print(f"   Service: {error['service']}")
        print(f"   Function: {error['function']}")
        
        if error['position_id']:
            print(f"   Position: {error['position_id']}")
        if error['order_ref']:
            print(f"   Order: {error['order_ref']}")
        if error['strategy_id']:
            print(f"   Strategy: {error['strategy_id']}")
        
        # Show context data if available
        if error['context_data']:
            try:
                context = json.loads(error['context_data'])
                print(f"   Context: {json.dumps(context, indent=6)}")
            except:
                print(f"   Context: {error['context_data']}")
        
        print("-" * 80)

def view_timestop_errors():
    """View only timestop-related errors"""
    errors_file = Path("Logs/errors.csv")
    
    if not errors_file.exists():
        print("❌ No errors.csv file found in Logs/ directory")
        return
    
    print("⏰ Timestop Errors:")
    print("=" * 80)
    
    with open(errors_file, 'r') as f:
        reader = csv.DictReader(f)
        errors = list(reader)
    
    timestop_errors = [e for e in errors if 'timestop' in e['function'].lower()]
    
    if not timestop_errors:
        print("✅ No timestop errors found")
        return
    
    for i, error in enumerate(timestop_errors, 1):
        print(f"\n🔴 Timestop Error #{i}:")
        print(f"   Time: {error['timestamp']}")
        print(f"   Type: {error['error_type']}")
        print(f"   Message: {error['error_message']}")
        print(f"   Position: {error['position_id']}")
        print(f"   Action: {error['function']}")
        
        if error['context_data']:
            try:
                context = json.loads(error['context_data'])
                print(f"   Context: {json.dumps(context, indent=6)}")
            except:
                print(f"   Context: {error['context_data']}")
        
        print("-" * 80)

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        if sys.argv[1] == "timestop":
            view_timestop_errors()
        else:
            try:
                limit = int(sys.argv[1])
                view_errors(limit)
            except ValueError:
                print("Usage: python view_errors.py [limit|timestop]")
    else:
        view_errors()
