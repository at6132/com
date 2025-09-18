#!/usr/bin/env python3
"""
Performance Testing Script for ATQ Ventures COM
Measures end-to-end order processing latency and identifies bottlenecks
"""

import asyncio
import time
import statistics
import requests
import hmac
import hashlib
import json
from typing import List, Dict, Tuple
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor
import threading

@dataclass
class PerformanceMetrics:
    """Performance measurement results"""
    operation: str
    min_time: float
    max_time: float
    avg_time: float
    median_time: float
    p95_time: float
    p99_time: float
    total_requests: int
    success_count: int
    error_count: int
    errors: List[str]

class COMPerformanceTester:
    def __init__(self, base_url: str, api_key: str, secret_key: str):
        self.base_url = base_url
        self.api_key = api_key
        self.secret_key = secret_key
        self.session = requests.Session()
        
    def create_hmac_signature(self, timestamp: int, method: str, path: str, body: str) -> str:
        """Create HMAC signature for authentication"""
        base_string = f"{timestamp}\n{method}\n{path}\n{body}"
        signature = hmac.new(
            self.secret_key.encode('utf-8'),
            base_string.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        return signature
    
    def create_order_payload(self, order_id: int) -> Dict:
        """Create a test order payload"""
        return {
            "idempotency_key": f"perf_test_{order_id}_{int(time.time())}",
            "environment": {
                "sandbox": True
            },
            "source": {
                "strategy_id": "performance_test",
                "instance_id": f"test_instance_{order_id}",
                "owner": "perf_tester"
            },
            "order": {
                "instrument": {
                    "class": "crypto_perp",
                    "symbol": "BTC_USDT"
                },
                "side": "BUY",
                "quantity": {
                    "type": "contracts",
                    "value": 0.0001
                },
                "order_type": "LIMIT",
                "price": 50000.0,
                "time_in_force": "GTC",
                "flags": {
                    "post_only": True,
                    "reduce_only": False,
                    "hidden": False,
                    "iceberg": {},
                    "allow_partial_fills": True
                },
                "routing": {
                    "mode": "AUTO"
                },
                "leverage": {
                    "enabled": False
                }
            }
        }
    
    def send_order(self, order_id: int) -> Tuple[float, bool, str]:
        """Send a single order and measure time"""
        start_time = time.time()
        
        try:
            # Prepare request
            method = "POST"
            path = "/api/v1/orders/orders"
            timestamp = int(time.time())
            payload = self.create_order_payload(order_id)
            body = json.dumps(payload)
            
            # Generate signature
            signature = self.create_hmac_signature(timestamp, method, path, body)
            auth_header = f'HMAC key_id="{self.api_key}", signature="{signature}", ts={timestamp}'
            
            # Send request
            headers = {
                "Authorization": auth_header,
                "Content-Type": "application/json"
            }
            
            response = self.session.post(
                f"{self.base_url}{path}",
                json=payload,
                headers=headers,
                timeout=30
            )
            
            end_time = time.time()
            latency = (end_time - start_time) * 1000  # Convert to milliseconds
            
            if response.status_code == 200:
                return latency, True, "Success"
            else:
                return latency, False, f"HTTP {response.status_code}: {response.text}"
                
        except Exception as e:
            end_time = time.time()
            latency = (end_time - start_time) * 1000
            return latency, False, str(e)
    
    def test_single_order_latency(self, num_orders: int = 10) -> PerformanceMetrics:
        """Test single order latency with multiple orders"""
        print(f"🔍 Testing Single Order Latency ({num_orders} orders)...")
        
        latencies = []
        success_count = 0
        error_count = 0
        errors = []
        
        for i in range(num_orders):
            latency, success, message = self.send_order(i)
            latencies.append(latency)
            
            if success:
                success_count += 1
                print(f"  ✅ Order {i+1}: {latency:.2f}ms")
            else:
                error_count += 1
                errors.append(message)
                print(f"  ❌ Order {i+1}: {latency:.2f}ms - {message}")
            
            # Small delay between orders
            time.sleep(0.1)
        
        return self._calculate_metrics("Single Order", latencies, success_count, error_count, errors)
    
    def test_concurrent_orders(self, num_orders: int = 10, max_workers: int = 5) -> PerformanceMetrics:
        """Test concurrent order processing"""
        print(f"🚀 Testing Concurrent Orders ({num_orders} orders, {max_workers} workers)...")
        
        latencies = []
        success_count = 0
        error_count = 0
        errors = []
        
        def send_order_wrapper(order_id):
            return self.send_order(order_id)
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [executor.submit(send_order_wrapper, i) for i in range(num_orders)]
            
            for i, future in enumerate(futures):
                try:
                    latency, success, message = future.result()
                    latencies.append(latency)
                    
                    if success:
                        success_count += 1
                        print(f"  ✅ Concurrent Order {i+1}: {latency:.2f}ms")
                    else:
                        error_count += 1
                        errors.append(message)
                        print(f"  ❌ Concurrent Order {i+1}: {latency:.2f}ms - {message}")
                        
                except Exception as e:
                    error_count += 1
                    errors.append(str(e))
                    print(f"  ❌ Concurrent Order {i+1}: Exception - {e}")
        
        return self._calculate_metrics("Concurrent Orders", latencies, success_count, error_count, errors)
    
    def test_endpoint_latency(self, endpoint: str, method: str = "GET") -> PerformanceMetrics:
        """Test specific endpoint latency"""
        print(f"🌐 Testing {method} {endpoint} latency...")
        
        latencies = []
        success_count = 0
        error_count = 0
        errors = []
        
        for i in range(20):  # Test 20 times
            start_time = time.time()
            
            try:
                if method == "GET":
                    response = self.session.get(f"{self.base_url}{endpoint}", timeout=10)
                elif method == "POST":
                    response = self.session.post(f"{self.base_url}{endpoint}", timeout=10)
                
                end_time = time.time()
                latency = (end_time - start_time) * 1000
                latencies.append(latency)
                
                if response.status_code == 200:
                    success_count += 1
                    print(f"  ✅ Request {i+1}: {latency:.2f}ms")
                else:
                    error_count += 1
                    errors.append(f"HTTP {response.status_code}")
                    print(f"  ❌ Request {i+1}: {latency:.2f}ms - HTTP {response.status_code}")
                    
            except Exception as e:
                error_count += 1
                errors.append(str(e))
                print(f"  ❌ Request {i+1}: Exception - {e}")
            
            time.sleep(0.05)  # Small delay
        
        return self._calculate_metrics(f"{method} {endpoint}", latencies, success_count, error_count, errors)
    
    def _calculate_metrics(self, operation: str, latencies: List[float], 
                          success_count: int, error_count: int, errors: List[str]) -> PerformanceMetrics:
        """Calculate performance metrics from latency data"""
        if not latencies:
            return PerformanceMetrics(
                operation=operation,
                min_time=0, max_time=0, avg_time=0, median_time=0,
                p95_time=0, p99_time=0, total_requests=0,
                success_count=success_count, error_count=error_count, errors=errors
            )
        
        latencies.sort()
        total_requests = len(latencies)
        
        return PerformanceMetrics(
            operation=operation,
            min_time=min(latencies),
            max_time=max(latencies),
            avg_time=statistics.mean(latencies),
            median_time=statistics.median(latencies),
            p95_time=latencies[int(0.95 * total_requests)] if total_requests > 0 else 0,
            p99_time=latencies[int(0.99 * total_requests)] if total_requests > 0 else 0,
            total_requests=total_requests,
            success_count=success_count,
            error_count=error_count,
            errors=errors
        )
    
    def print_metrics(self, metrics: PerformanceMetrics):
        """Print performance metrics in a formatted way"""
        print(f"\n📊 {metrics.operation} Performance Results:")
        print(f"   Total Requests: {metrics.total_requests}")
        print(f"   Success Rate: {metrics.success_count}/{metrics.total_requests} ({metrics.success_count/metrics.total_requests*100:.1f}%)")
        print(f"   Error Rate: {metrics.error_count}/{metrics.total_requests} ({metrics.error_count/metrics.total_requests*100:.1f}%)")
        
        if metrics.total_requests > 0:
            print(f"   Latency (ms):")
            print(f"     Min:     {metrics.min_time:.2f}")
            print(f"     Max:     {metrics.max_time:.2f}")
            print(f"     Average: {metrics.avg_time:.2f}")
            print(f"     Median:  {metrics.median_time:.2f}")
            print(f"     95th %:  {metrics.p95_time:.2f}")
            print(f"     99th %:  {metrics.p99_time:.2f}")
        
        if metrics.errors:
            print(f"   Errors: {metrics.errors[:3]}")  # Show first 3 errors
    
    def run_full_performance_test(self):
        """Run complete performance test suite"""
        print("🚀 ATQ Ventures COM - Performance Test Suite")
        print("=" * 60)
        
        # Test 1: Health endpoint (baseline)
        health_metrics = self.test_endpoint_latency("/health")
        self.print_metrics(health_metrics)
        
        # Test 2: Single order latency
        single_order_metrics = self.test_single_order_latency(num_orders=5)
        self.print_metrics(single_order_metrics)
        
        # Test 3: Concurrent orders
        concurrent_metrics = self.test_concurrent_orders(num_orders=5, max_workers=3)
        self.print_metrics(concurrent_metrics)
        
        # Test 4: System status endpoint
        status_metrics = self.test_endpoint_latency("/ready")
        self.print_metrics(status_metrics)
        
        # Summary
        print("\n" + "=" * 60)
        print("📈 PERFORMANCE SUMMARY")
        print("=" * 60)
        
        all_metrics = [health_metrics, single_order_metrics, concurrent_metrics, status_metrics]
        
        for metrics in all_metrics:
            if metrics.total_requests > 0:
                print(f"{metrics.operation}:")
                print(f"  Average Latency: {metrics.avg_time:.2f}ms")
                print(f"  95th Percentile: {metrics.p95_time:.2f}ms")
                print(f"  Success Rate: {metrics.success_count/metrics.total_requests*100:.1f}%")
                print()
        
        # Performance analysis
        print("🔍 PERFORMANCE ANALYSIS:")
        if single_order_metrics.avg_time > 1000:  # > 1 second
            print("  ❌ CRITICAL: Order processing is too slow (>1s)")
            print("     - Database operations likely blocking")
            print("     - MEXC API calls may be slow")
            print("     - Need async optimization")
        elif single_order_metrics.avg_time > 100:  # > 100ms
            print("  ⚠️  WARNING: Order processing is slow (>100ms)")
            print("     - Should be <50ms for HFT")
            print("     - Consider database optimization")
        else:
            print("  ✅ GOOD: Order processing is within acceptable range")
        
        if concurrent_metrics.avg_time > single_order_metrics.avg_time * 1.5:
            print("  ⚠️  WARNING: Concurrent processing shows bottlenecks")
            print("     - System may not handle load well")
            print("     - Consider connection pooling")

def main():
    """Main function to run performance tests"""
    # Configuration
    BASE_URL = "http://localhost:8000"
    
    # Load API keys from file
    try:
        with open("keys/test_strategy_keys.json", "r") as f:
            keys = json.load(f)
            API_KEY = keys["api_key"]
            SECRET_KEY = keys["secret_key"]
    except FileNotFoundError:
        print("❌ Error: keys/test_strategy_keys.json file not found!")
        print("Please generate API keys first using: python quick_generate_keys.py")
        return
    except KeyError as e:
        print(f"❌ Error: Missing key in test_strategy_keys.json file: {e}")
        return
    
    # Check if COM server is running
    try:
        response = requests.get(f"{BASE_URL}/health", timeout=5)
        if response.status_code != 200:
            print(f"❌ Error: COM server not responding properly: {response.status_code}")
            return
    except requests.exceptions.RequestException:
        print("❌ Error: Cannot connect to COM server!")
        print(f"Make sure the server is running at: {BASE_URL}")
        return
    
    print("✅ COM server is running and accessible")
    
    # Run performance tests
    tester = COMPerformanceTester(BASE_URL, API_KEY, SECRET_KEY)
    tester.run_full_performance_test()

if __name__ == "__main__":
    main()
