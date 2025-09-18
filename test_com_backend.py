"""
Test script for COM backend
Tests the complete order creation flow
"""
import asyncio
import sys
import os
from datetime import datetime

# Add the project root to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

async def test_order_creation():
    """Test order creation flow"""
    print("=== Testing Order Creation Flow ===")
    
    try:
        from com.app.schemas.orders import CreateOrderRequest
        from com.app.schemas.base import (
            Environment, OrderRequest, Instrument, InstrumentClass,
            OrderSide, OrderType, TimeInForce, Flags, Routing, RoutingMode, Leverage
        )
        from com.app.services.orders import order_service
        
        print("✅ Schemas imported successfully")
        
        # Create test order request
        order_request = CreateOrderRequest(
            idempotency_key="test_key_12345",
            environment=Environment(sandbox=True),
            source={
                "strategy_id": "test_strategy",
                "instance_id": "test_instance",
                "owner": "test_owner"
            },
            order=OrderRequest(
                instrument=Instrument(
                    class_=InstrumentClass.CRYPTO_PERP,
                    symbol="BTC_USDT"
                ),
                side=OrderSide.BUY,
                quantity={
                    "type": "contracts",
                    "value": 0.001
                },
                order_type=OrderType.LIMIT,
                price=50000.0,
                time_in_force=TimeInForce.GTC,
                flags=Flags(
                    post_only=True,
                    reduce_only=False,
                    hidden=False,
                    iceberg={},
                    allow_partial_fills=True
                ),
                routing=Routing(mode=RoutingMode.AUTO),
                leverage=Leverage(enabled=False)
            )
        )
        
        print("✅ Test order request created")
        print(f"   Symbol: {order_request.order.instrument.symbol}")
        print(f"   Side: {order_request.order.side.value}")
        print(f"   Type: {order_request.order.order_type.value}")
        print(f"   Price: {order_request.order.price}")
        print(f"   Quantity: {order_request.order.quantity.value}")
        
        # Test order creation
        print("\n🔍 Testing order creation...")
        result, ack, error = await order_service.create_order(order_request)
        
        if result.success:
            print("✅ Order created successfully!")
            print(f"   Order Ref: {result.order_ref}")
            print(f"   Position Ref: {result.position_ref}")
            print(f"   Broker Order ID: {result.broker_order_id}")
            if result.adjustments:
                print(f"   Adjustments: {result.adjustments}")
        elif error:
            print(f"❌ Order creation failed with error:")
            print(f"   Code: {error.error['code']}")
            print(f"   Message: {error.error['message']}")
        else:
            print("❌ Unexpected result from order service")
        
        return result.success
        
    except Exception as e:
        print(f"❌ Error testing order creation: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_broker_integration():
    """Test broker integration"""
    print("\n=== Testing Broker Integration ===")
    
    try:
        from com.app.adapters.manager import broker_manager
        
        # Check available brokers
        available_brokers = broker_manager.get_enabled_brokers()
        print(f"✅ Found {len(available_brokers)} enabled brokers:")
        
        for name, config in available_brokers.items():
            print(f"   - {name}: {config.environment} ({'testnet' if config.testnet else 'live'})")
        
        # Test MEXC specifically
        mexc_config = broker_manager.get_broker("mexc")
        if mexc_config:
            print(f"\n🔍 Testing MEXC configuration:")
            print(f"   Base URL: {mexc_config.base_url}")
            print(f"   Environment: {mexc_config.environment}")
            print(f"   Testnet: {mexc_config.testnet}")
            print(f"   Futures: {mexc_config.futures}")
            
            # Check symbol support
            crypto_perp = mexc_config.markets.get("crypto_perp", {})
            symbols = crypto_perp.get("symbols", {})
            print(f"   Supported symbols: {len(symbols)}")
            
            # Test specific symbol
            if "BTC_USDT" in symbols:
                btc_config = symbols["BTC_USDT"]
                print(f"   BTC_USDT config:")
                print(f"     Tick size: {btc_config.get('tick_size')}")
                print(f"     Lot size: {btc_config.get('lot_size')}")
                print(f"     Min order: {btc_config.get('min_order_size')}")
                print(f"     Max leverage: {btc_config.get('max_leverage')}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error testing broker integration: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_schema_validation():
    """Test schema validation"""
    print("\n=== Testing Schema Validation ===")
    
    try:
        from com.app.schemas.base import OrderRequest, Instrument, InstrumentClass, OrderSide, OrderType, TimeInForce, Flags, Routing, RoutingMode, Leverage
        
        # Test valid order
        valid_order = OrderRequest(
            instrument=Instrument(
                class_=InstrumentClass.CRYPTO_PERP,
                symbol="BTC_USDT"
            ),
            side=OrderSide.BUY,
            quantity={
                "type": "contracts",
                "value": 0.001
            },
            order_type=OrderType.LIMIT,
            price=50000.0,
            time_in_force=TimeInForce.GTC,
            flags=Flags(
                post_only=True,
                reduce_only=False,
                hidden=False,
                iceberg={},
                allow_partial_fills=True
            ),
            routing=Routing(mode=RoutingMode.AUTO),
            leverage=Leverage(enabled=False)
        )
        
        print("✅ Valid order created successfully")
        
        # Test invalid order (missing price for LIMIT)
        try:
            invalid_order = OrderRequest(
                instrument=Instrument(
                    class_=InstrumentClass.CRYPTO_PERP,
                    symbol="BTC_USDT"
                ),
                side=OrderSide.BUY,
                quantity={
                    "type": "contracts",
                    "value": 0.001
                },
                order_type=OrderType.LIMIT,
                # Missing price - should fail validation
                time_in_force=TimeInForce.GTC,
                flags=Flags(
                    post_only=True,
                    reduce_only=False,
                    hidden=False,
                    iceberg={},
                    allow_partial_fills=True
                ),
                routing=Routing(mode=RoutingMode.AUTO),
                leverage=Leverage(enabled=False)
            )
            print("❌ Invalid order should have failed validation")
            return False
        except ValueError as e:
            print(f"✅ Invalid order correctly rejected: {e}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error testing schema validation: {e}")
        import traceback
        traceback.print_exc()
        return False

async def main():
    """Run all tests"""
    print("🚀 COM Backend Test Suite")
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    tests = [
        ("Schema Validation", test_schema_validation),
        ("Broker Integration", test_broker_integration),
        ("Order Creation Flow", test_order_creation)
    ]
    
    results = []
    
    for test_name, test_func in tests:
        print(f"\n🔍 Running: {test_name}")
        try:
            result = await test_func()
            results.append((test_name, result))
            status = "✅ PASSED" if result else "❌ FAILED"
            print(f"{status} {test_name}")
        except Exception as e:
            print(f"💥 ERROR in {test_name}: {e}")
            results.append((test_name, False))
    
    # Summary
    print("\n" + "=" * 60)
    print("📊 TEST SUMMARY")
    print("=" * 60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✅ PASSED" if result else "❌ FAILED"
        print(f"{test_name}: {status}")
    
    print(f"\nOverall: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests passed! COM backend is working correctly.")
    elif passed > total // 2:
        print("⚠️  Most tests passed. Check failed tests for issues.")
    else:
        print("💥 Many tests failed. Check configuration and implementation.")
    
    print(f"\nCompleted at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

if __name__ == "__main__":
    asyncio.run(main())
