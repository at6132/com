#!/usr/bin/env python3
"""
Quick Performance Test for COM Order Latency
Simple script to measure order processing time
"""

import time
import requests
import hmac
import hashlib
import json

def create_hmac_signature(secret_key: str, timestamp: int, method: str, path: str, body: str) -> str:
    """Create HMAC signature"""
    base_string = f"{timestamp}\n{method}\n{path}\n{body}"
    return hmac.new(
        secret_key.encode('utf-8'),
        base_string.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()

def test_order_latency(base_url: str, api_key: str, secret_key: str, num_tests: int = 5):
    """Test order processing latency"""
    print(f"🚀 Testing COM Order Latency ({num_tests} orders)")
    print("=" * 50)
    
    latencies = []
    errors = []
    
    for i in range(num_tests):
        print(f"\n📝 Test {i+1}/{num_tests}")
        
        # Create order payload
        payload = {
            "idempotency_key": f"perf_test_{i}_{int(time.time())}",
            "environment": {"sandbox": True},
            "source": {
                "strategy_id": "perf_test",
                "instance_id": f"test_{i}",
                "owner": "tester"
            },
            "order": {
                "instrument": {"class": "crypto_perp", "symbol": "BTC_USDT"},
                "side": "BUY",
                "quantity": {"type": "contracts", "value": 0.0001},
                "order_type": "LIMIT",
                "price": 50000.0,
                "time_in_force": "GTC",
                "flags": {"post_only": True, "reduce_only": False, "hidden": False, "iceberg": {}, "allow_partial_fills": True},
                "routing": {"mode": "AUTO"},
                "leverage": {"enabled": False}
            }
        }
        
        # Prepare request
        method = "POST"
        path = "/api/v1/orders/orders"
        timestamp = int(time.time())
        body = json.dumps(payload)
        
        # Generate signature
        signature = create_hmac_signature(secret_key, timestamp, method, path, body)
        auth_header = f'HMAC key_id="{api_key}", signature="{signature}", ts={timestamp}'
        
        headers = {
            "Authorization": auth_header,
            "Content-Type": "application/json"
        }
        
        # Measure time
        start_time = time.time()
        
        try:
            response = requests.post(
                f"{base_url}{path}",
                json=payload,
                headers=headers,
                timeout=30
            )
            
            end_time = time.time()
            latency_ms = (end_time - start_time) * 1000
            latencies.append(latency_ms)
            
            if response.status_code == 200:
                print(f"  ✅ Success: {latency_ms:.2f}ms")
                print(f"     Response: {response.text[:100]}...")
            else:
                print(f"  ❌ HTTP {response.status_code}: {latency_ms:.2f}ms")
                print(f"     Error: {response.text}")
                errors.append(f"HTTP {response.status_code}")
                
        except Exception as e:
            end_time = time.time()
            latency_ms = (end_time - start_time) * 1000
            print(f"  ❌ Exception: {latency_ms:.2f}ms - {e}")
            errors.append(str(e))
        
        # Small delay between tests
        time.sleep(0.5)
    
    # Results
    print("\n" + "=" * 50)
    print("📊 PERFORMANCE RESULTS")
    print("=" * 50)
    
    if latencies:
        print(f"Total Tests: {num_tests}")
        print(f"Successful: {len(latencies)}")
        print(f"Errors: {len(errors)}")
        print()
        
        print("Latency (milliseconds):")
        print(f"  Min:     {min(latencies):.2f}")
        print(f"  Max:     {max(latencies):.2f}")
        print(f"  Average: {sum(latencies)/len(latencies):.2f}")
        print(f"  Median:  {sorted(latencies)[len(latencies)//2]:.2f}")
        
        # Performance analysis
        avg_latency = sum(latencies)/len(latencies)
        print()
        print("🔍 ANALYSIS:")
        
        if avg_latency > 1000:
            print("  ❌ CRITICAL: Too slow (>1s) - Need immediate optimization")
        elif avg_latency > 100:
            print("  ⚠️  SLOW: Should be <50ms for HFT")
        elif avg_latency > 50:
            print("  ⚠️  ACCEPTABLE: Could be faster for HFT")
        else:
            print("  ✅ GOOD: Within HFT requirements")
            
    if errors:
        print(f"\n❌ Errors encountered: {errors[:3]}")

def main():
    """Main function"""
    BASE_URL = "http://localhost:8000"
    
    # Load API keys
    try:
        with open("keys/test_strategy_keys.json", "r") as f:
            keys = json.load(f)
            API_KEY = keys["api_key"]
            SECRET_KEY = keys["secret_key"]
    except FileNotFoundError:
        print("❌ Error: keys/test_strategy_keys.json file not found!")
        print("Run: python quick_generate_keys.py")
        return
    
    # Check server
    try:
        response = requests.get(f"{BASE_URL}/health", timeout=5)
        if response.status_code != 200:
            print(f"❌ Server error: {response.status_code}")
            return
    except:
        print(f"❌ Cannot connect to {BASE_URL}")
        print("Make sure COM server is running")
        return
    
    print("✅ COM server is accessible")
    
    # Run test
    test_order_latency(BASE_URL, API_KEY, SECRET_KEY, num_tests=5)

if __name__ == "__main__":
    main()
