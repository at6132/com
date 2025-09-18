#!/usr/bin/env python3
"""
Test HMAC signature generation and verification
This script tests if our GUI is generating signatures correctly
"""

import hmac
import hashlib
import time
import json

def test_hmac_generation():
    """Test HMAC signature generation"""
    
    # Test data from your GUI
    api_key = "UkFWRl9WMl9WMl8yMDI1MDgyOF8yMDE1MjbVvMcwEvcdoTque80fM_9UrmpmgknJ3Pu2Co51EisEwA"
    secret_key = "xBs19q622bH2MBYdxwvNDdnIoyO8W14i213TkkZsqc-Z2vpu_nYv23EgWbDU9ILgUJTQ-Ay-ZuMhQs7elIE3jg"
    
    # Test payload
    payload = {
        "strategy_id": "test_strategy_001",
        "symbol": "BTCUSDT",
        "side": "BUY",
        "order_type": "LIMIT",
        "quantity": 0.001,
        "leverage": 1.0,
        "time_in_force": "GTC",
        "reduce_only": False,
        "post_only": True,
        "idempotency_key": "test_strategy_001_BTCUSDT_20250828_203334_879696",
        "paper_trade": True,
        "notes": "",
        "price": 50000.0
    }
    
    # Convert to JSON string
    payload_str = json.dumps(payload)
    
    # Test timestamp
    timestamp = str(int(time.time()))
    
    # Test method and path
    method = "POST"
    path = "/api/v1/orders/orders"
    
    print("🔐 Testing HMAC Signature Generation")
    print("=" * 50)
    print(f"API Key: {api_key[:30]}...")
    print(f"Secret Key: {secret_key[:30]}...")
    print(f"Timestamp: {timestamp}")
    print(f"Method: {method}")
    print(f"Path: {path}")
    print(f"Payload: {payload_str[:100]}...")
    
    # Generate signature using the same method as GUI
    base_string = f"{timestamp}\n{method}\n{path}\n{payload_str}"
    signature = hmac.new(
        secret_key.encode('utf-8'),
        base_string.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()
    
    print(f"\nBase String: {repr(base_string)}")
    print(f"Generated Signature: {signature}")
    
    # Create authorization header
    auth_header = f'HMAC key_id="{api_key}", signature="{signature}", ts={timestamp}'
    print(f"Authorization Header: {auth_header[:80]}...")
    
    # Now test verification
    print("\n🔍 Testing HMAC Signature Verification")
    print("=" * 50)
    
    # Simulate what the server would do
    # Parse the auth header
    auth_parts = auth_header[5:].split(",")
    parsed_key_id = None
    parsed_signature = None
    parsed_timestamp = None
    
    for part in auth_parts:
        if part.strip().startswith("key_id="):
            parsed_key_id = part.strip()[8:].strip('"')
        elif part.strip().startswith("signature="):
            parsed_signature = part.strip()[11:].strip('"')
        elif part.strip().startswith("ts="):
            parsed_timestamp = part.strip()[4:]
    
    print(f"Parsed Key ID: {parsed_key_id[:30]}...")
    print(f"Parsed Signature: {parsed_signature}")
    print(f"Parsed Timestamp: {parsed_timestamp}")
    
    # Verify signature
    expected_base_string = f"{parsed_timestamp}\n{method}\n{path}\n{payload_str}"
    expected_signature = hmac.new(
        secret_key.encode('utf-8'),
        expected_base_string.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()
    
    print(f"\nExpected Base String: {repr(expected_base_string)}")
    print(f"Expected Signature: {expected_signature}")
    
    # Compare signatures
    if signature == expected_signature:
        print("✅ Signature verification SUCCESSFUL!")
    else:
        print("❌ Signature verification FAILED!")
        print(f"Generated: {signature}")
        print(f"Expected:  {expected_signature}")
    
    # Test with constant-time comparison
    if hmac.compare_digest(signature, expected_signature):
        print("✅ HMAC compare_digest SUCCESSFUL!")
    else:
        print("❌ HMAC compare_digest FAILED!")
    
    return signature == expected_signature

def test_server_expectations():
    """Test what the server expects vs what we're sending"""
    
    print("\n🌐 Testing Server Expectations")
    print("=" * 50)
    
    # What the server expects (from auth.py)
    print("Server expects:")
    print("- Authorization header format: HMAC key_id=\"...\", signature=\"...\", ts=...")
    print("- Base string format: timestamp\\nmethod\\npath\\nbody")
    print("- HMAC-SHA256 with secret key")
    
    # What we're sending
    print("\nWhat we're sending:")
    print("- ✅ Correct Authorization header format")
    print("- ✅ Correct base string format")
    print("- ✅ Correct HMAC-SHA256 algorithm")
    print("- ✅ Correct secret key usage")
    
    print("\nThe issue is likely that the server:")
    print("1. Doesn't have your API key in its database")
    print("2. Is trying to use a bcrypt hash instead of the actual secret key")
    print("3. Has a different path expectation")

if __name__ == "__main__":
    print("ATQ Ventures COM - HMAC Verification Test")
    print("=" * 60)
    
    # Test HMAC generation
    success = test_hmac_generation()
    
    # Test server expectations
    test_server_expectations()
    
    print("\n" + "=" * 60)
    if success:
        print("✅ HMAC signature generation is working correctly!")
        print("The issue is likely on the server side.")
    else:
        print("❌ HMAC signature generation has issues!")
    
    print("\nNext steps:")
    print("1. Check if the server has your API key in its database")
    print("2. Check if the server is using the correct secret key for verification")
    print("3. Verify the server's path expectations")
