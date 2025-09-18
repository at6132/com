#!/usr/bin/env python3
"""
Test Authentication for ATQ Ventures COM
Test the HMAC authentication system with generated keys
"""

import json
import time
import hmac
import hashlib
import requests
import os

def test_authentication():
    """Test the authentication system"""
    
    # Check if keys exist
    keys_dir = "keys"
    if not os.path.exists(keys_dir):
        print("❌ Keys directory not found. Run generate_keys.py first.")
        return
    
    # Find a key file
    key_files = [f for f in os.listdir(keys_dir) if f.endswith('_keys.json')]
    if not key_files:
        print("❌ No key files found. Run generate_keys.py first.")
        return
    
    # Load the first key file
    key_file = os.path.join(keys_dir, key_files[0])
    print(f"🔑 Loading keys from: {key_file}")
    
    with open(key_file, 'r') as f:
        key_data = json.load(f)
    
    api_key = key_data['api_key']
    secret_key = key_data['secret_key']
    
    print(f"✅ Loaded API Key: {api_key[:20]}...")
    print(f"✅ Loaded Secret Key: {secret_key[:20]}...")
    
    # Test payload
    test_payload = {
        "strategy_id": "test_strategy_001",
        "symbol": "BTCUSDT",
        "side": "BUY",
        "order_type": "LIMIT",
        "quantity": 0.001,
        "price": 50000,
        "time_in_force": "GTC",
        "reduce_only": False,
        "post_only": True,
        "idempotency_key": f"test_{int(time.time())}",
        "paper_trade": True,
        "notes": "Test order from auth test script"
    }
    
    print(f"\n📋 Test Payload:")
    print(json.dumps(test_payload, indent=2))
    
    # Generate authentication
    payload_str = json.dumps(test_payload)
    timestamp = str(int(time.time()))
    
    # Generate HMAC signature
    message = f"{timestamp}{payload_str}"
    signature = hmac.new(
        secret_key.encode('utf-8'),
        message.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()
    
    print(f"\n🔐 Authentication Details:")
    print(f"Timestamp: {timestamp}")
    print(f"Message: {message[:50]}...")
    print(f"Signature: {signature}")
    
    # Test headers
    headers = {
        "Content-Type": "application/json",
        "X-API-Key": api_key,
        "X-Timestamp": timestamp,
        "X-Signature": signature
    }
    
    print(f"\n📤 Request Headers:")
    for key, value in headers.items():
        if key == "X-API-Key" or key == "X-Signature":
            print(f"  {key}: {value[:20]}...")
        else:
            print(f"  {key}: {value}")
    
    # Test with COM server (if available)
    com_url = "http://localhost:8000"
    
    print(f"\n🌐 Testing connection to COM server...")
    
    try:
        # Test health endpoint first
        health_response = requests.get(f"{com_url}/health", timeout=5)
        if health_response.status_code == 200:
            print("✅ COM server is running and responding")
            
            # Test order endpoint
            print("📤 Sending test order...")
            order_response = requests.post(
                f"{com_url}/api/v1/orders/orders",
                json=test_payload,
                headers=headers,
                timeout=10
            )
            
            print(f"📥 Response Status: {order_response.status_code}")
            print(f"📥 Response Body: {order_response.text}")
            
            if order_response.status_code in [200, 201]:
                print("✅ Authentication successful! Order sent to COM server.")
            else:
                print("❌ Order request failed. Check server logs for details.")
                
        else:
            print(f"⚠️  COM server responded with status: {health_response.status_code}")
            
    except requests.exceptions.ConnectionError:
        print("❌ Could not connect to COM server. Is it running?")
        print("💡 The authentication system is working, but the server is not available.")
        
    except Exception as e:
        print(f"❌ Error testing authentication: {e}")
    
    print(f"\n📋 Authentication Test Complete!")
    print(f"💡 Use these keys in your GUI configuration to test orders.")

if __name__ == "__main__":
    print("🔐 ATQ Ventures COM - Authentication Test")
    print("="*50)
    test_authentication()
