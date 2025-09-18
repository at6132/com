"""
Broker manager for handling multiple broker adapters
Provides unified interface for order execution across brokers
"""
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime

from .base import BrokerAdapter
from .mexc import MEXCAdapter
from ..config.brokers import broker_registry, BrokerConfig

logger = logging.getLogger(__name__)

class BrokerManager:
    """Manages multiple broker adapters"""
    
    def __init__(self):
        self.adapters: Dict[str, BrokerAdapter] = {}
        self._initialized = False
    
    async def initialize(self):
        """Initialize all enabled broker adapters"""
        if self._initialized:
            return
        
        enabled_brokers = broker_registry.get_enabled_brokers()
        
        for broker_name, config in enabled_brokers.items():
            try:
                adapter = await self._create_adapter(broker_name, config)
                if adapter:
                    self.adapters[broker_name] = adapter
                    logger.info(f"Initialized broker adapter: {broker_name}")
            except Exception as e:
                logger.error(f"Failed to initialize broker {broker_name}: {e}")
        
        self._initialized = True
        logger.info(f"Broker manager initialized with {len(self.adapters)} adapters")
    
    async def initialize_lazy(self):
        """Lazy initialization - just mark as initialized without connecting"""
        if self._initialized:
            return
        
        logger.info("Lazy initialization - broker adapters will connect on first use")
        self._initialized = True
        logger.info("Broker manager initialized (lazy mode)")
    
    async def ensure_broker_connected(self, broker_name: str):
        """Ensure a specific broker is connected, creating adapter if needed"""
        if broker_name in self.adapters:
            return  # Already connected
        
        enabled_brokers = broker_registry.get_enabled_brokers()
        if broker_name not in enabled_brokers:
            raise ValueError(f"Broker {broker_name} not found in enabled brokers")
        
        try:
            adapter = await self._create_adapter(broker_name, enabled_brokers[broker_name])
            if adapter:
                self.adapters[broker_name] = adapter
                logger.info(f"Lazy-connected broker adapter: {broker_name}")
            else:
                raise RuntimeError(f"Failed to create adapter for {broker_name}")
        except Exception as e:
            logger.error(f"Failed to lazy-connect broker {broker_name}: {e}")
            raise
    
    async def _create_adapter(self, broker_name: str, config: BrokerConfig) -> Optional[BrokerAdapter]:
        """Create broker adapter based on configuration"""
        try:
            if broker_name == "mexc":
                adapter = MEXCAdapter(config)
                # Use optimized connection (no expensive health check)
                if await adapter.connect():
                    return adapter
                else:
                    logger.error(f"Failed to connect to {broker_name}")
                    return None
            else:
                logger.warning(f"No adapter implementation for broker: {broker_name}")
                return None
        except Exception as e:
            logger.error(f"Error creating adapter for {broker_name}: {e}")
            return None
    
    async def shutdown(self):
        """Shutdown all broker adapters"""
        for broker_name, adapter in self.adapters.items():
            try:
                await adapter.disconnect()
                logger.info(f"Disconnected from broker: {broker_name}")
            except Exception as e:
                logger.error(f"Error disconnecting from {broker_name}: {e}")
        
        self.adapters.clear()
        self._initialized = False
        logger.info("Broker manager shutdown complete")
    
    def get_adapter(self, broker_name: str) -> Optional[BrokerAdapter]:
        """Get broker adapter by name"""
        return self.adapters.get(broker_name)
    
    def list_adapters(self) -> List[str]:
        """List all available broker adapters"""
        return list(self.adapters.keys())
    
    def get_enabled_brokers(self) -> Dict[str, BrokerConfig]:
        """Get all enabled broker configurations"""
        from ..config.brokers import broker_registry
        return broker_registry.get_enabled_brokers()
    
    async def health_check_all(self) -> Dict[str, bool]:
        """Check health of all broker adapters"""
        health_status = {}
        
        for broker_name, adapter in self.adapters.items():
            try:
                health_status[broker_name] = await adapter.health_check()
            except Exception as e:
                logger.error(f"Health check failed for {broker_name}: {e}")
                health_status[broker_name] = False
        
        return health_status
    
    async def route_order(self, order: Any, routing_config: Dict[str, Any]) -> Dict[str, Any]:
        """Route order to appropriate broker based on routing configuration"""
        routing_mode = routing_config.get("mode", "AUTO")
        
        if routing_mode == "DIRECT":
            broker_name = routing_config.get("direct", {}).get("broker")
            if not broker_name:
                return {
                    "success": False,
                    "error": "DIRECT routing requires broker specification"
                }
            
            adapter = self.get_adapter(broker_name)
            if not adapter:
                return {
                    "success": False,
                    "error": f"Broker {broker_name} not available"
                }
            
            return await adapter.place_order(order)
        
        elif routing_mode == "AUTO":
            # Auto-routing logic - for now, route to first available broker
            # In the future, this could implement smart routing based on:
            # - Best execution prices
            # - Lowest fees
            # - Best fill rates
            # - Geographic proximity
            
            available_brokers = list(self.adapters.keys())
            if not available_brokers:
                return {
                    "success": False,
                    "error": "No broker adapters available"
                }
            
            # For now, route to first available broker
            # TODO: Implement smart routing algorithm
            broker_name = available_brokers[0]
            adapter = self.adapters[broker_name]
            
            logger.info(f"Auto-routing order to {broker_name}")
            return await adapter.place_order(order)
        
        else:
            return {
                "success": False,
                "error": f"Unsupported routing mode: {routing_mode}"
            }
    
    async def get_aggregated_balances(self) -> Dict[str, float]:
        """Get aggregated balances across all brokers"""
        aggregated = {}
        
        for broker_name, adapter in self.adapters.items():
            try:
                balances = await adapter.get_balances()
                for currency, amount in balances.items():
                    if currency not in aggregated:
                        aggregated[currency] = 0.0
                    aggregated[currency] += amount
            except Exception as e:
                logger.error(f"Error getting balances from {broker_name}: {e}")
        
        return aggregated
    
    async def get_aggregated_positions(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get aggregated positions across all brokers"""
        aggregated = []
        
        for broker_name, adapter in self.adapters.items():
            try:
                positions = await adapter.get_positions(symbol)
                for position in positions:
                    position["broker"] = broker_name
                    aggregated.append(position)
            except Exception as e:
                logger.error(f"Error getting positions from {broker_name}: {e}")
        
        return aggregated
    
    def get_broker_features(self, broker_name: str) -> Dict[str, Any]:
        """Get features supported by a specific broker"""
        adapter = self.get_adapter(broker_name)
        if adapter:
            return adapter.config.features
        return {}
    
    def get_broker_market_info(self, broker_name: str, symbol: str) -> Dict[str, Any]:
        """Get market information for a specific broker and symbol"""
        adapter = self.get_adapter(broker_name)
        if adapter:
            return adapter.config.markets
        return {}

# Global broker manager instance
broker_manager = BrokerManager()
