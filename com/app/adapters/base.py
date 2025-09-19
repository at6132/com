"""
Base broker adapter interface
All broker adapters must implement this interface
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
from datetime import datetime
import logging
import math

from ..schemas.orders import OrderRequest, OrderView
from ..schemas.positions import SubOrderView

logger = logging.getLogger(__name__)
from ..config.brokers import BrokerConfig

class BrokerAdapter(ABC):
    """Base interface for all broker adapters"""
    
    def __init__(self, config: BrokerConfig):
        self.config = config
        self.name = config.name
    
    @abstractmethod
    async def connect(self) -> bool:
        """Connect to broker API"""
        pass
    
    @abstractmethod
    async def disconnect(self):
        """Disconnect from broker API"""
        pass
    
    @abstractmethod
    async def health_check(self) -> bool:
        """Check broker connectivity"""
        pass
    
    @abstractmethod
    async def place_order(self, order: OrderRequest) -> Dict[str, Any]:
        """Place a new order with the broker"""
        pass
    
    @abstractmethod
    async def amend_order(self, broker_order_id: str, changes: Dict[str, Any]) -> Dict[str, Any]:
        """Amend an existing order"""
        pass
    
    @abstractmethod
    async def cancel_order(self, broker_order_id: str) -> Dict[str, Any]:
        """Cancel an existing order"""
        pass
    
    @abstractmethod
    async def get_order(self, broker_order_id: str) -> Optional[Dict[str, Any]]:
        """Get order status from broker"""
        pass
    
    @abstractmethod
    async def get_balances(self) -> Dict[str, float]:
        """Get account balances"""
        pass
    
    @abstractmethod
    async def get_positions(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get current positions"""
        pass
    
    @abstractmethod
    async def get_market_data(self, symbol: str) -> Dict[str, Any]:
        """Get current market data (bid, ask, last, etc.)"""
        pass
    
    @abstractmethod
    async def get_features(self) -> Dict[str, Any]:
        """Get broker features and capabilities"""
        pass
    
    @abstractmethod
    async def get_market_info(self, symbol: str) -> Dict[str, Any]:
        """Get market information (tick size, lot size, etc.)"""
        pass
    
    # Utility methods
    def supports_feature(self, feature: str) -> bool:
        """Check if broker supports a specific feature"""
        return self.config.features.get(feature, False)
    
    def get_tick_size(self, symbol: str) -> Optional[float]:
        """Get tick size for a symbol"""
        for market_type, market_config in self.config.markets.items():
            symbols = market_config.get("symbols", {})
            if isinstance(symbols, dict) and symbol in symbols:
                return symbols[symbol].get("tick_size")
            elif isinstance(symbols, list) and symbol in symbols:
                return market_config.get("tick_size")  # Fallback for old format
        return None
    
    def get_lot_size(self, symbol: str) -> Optional[float]:
        """Get lot size for a symbol"""
        for market_type, market_config in self.config.markets.items():
            symbols = market_config.get("symbols", {})
            if isinstance(symbols, dict) and symbol in symbols:
                return symbols[symbol].get("lot_size")
            elif isinstance(symbols, list) and symbol in symbols:
                return market_config.get("lot_size")  # Fallback for old format
        return None
    
    def get_min_order_size(self, symbol: str) -> Optional[float]:
        """Get minimum order size for a symbol"""
        for market_type, market_config in self.config.markets.items():
            symbols = market_config.get("symbols", {})
            if isinstance(symbols, dict) and symbol in symbols:
                return symbols[symbol].get("min_order_size")
            elif isinstance(symbols, list) and symbol in symbols:
                return market_config.get("min_order_size")  # Fallback for old format
        return None
    
    def get_max_order_size(self, symbol: str) -> Optional[float]:
        """Get maximum order size for a symbol"""
        for market_type, market_config in self.config.markets.items():
            symbols = market_config.get("symbols", {})
            if isinstance(symbols, dict) and symbol in symbols:
                return symbols[symbol].get("max_order_size")
            elif isinstance(symbols, list) and symbol in symbols:
                return market_config.get("max_order_size")  # Fallback for old format
        return None
    
    def get_min_notional(self, symbol: str) -> Optional[float]:
        """Get minimum notional value for a symbol"""
        for market_type, market_config in self.config.markets.items():
            symbols = market_config.get("symbols", {})
            if isinstance(symbols, dict) and symbol in symbols:
                return symbols[symbol].get("min_notional")
            elif isinstance(symbols, list) and symbol in symbols:
                return market_config.get("min_notional")  # Fallback for old format
        return None
    
    def get_max_leverage(self, symbol: str) -> Optional[int]:
        """Get maximum leverage for a symbol"""
        for market_type, market_config in self.config.markets.items():
            symbols = market_config.get("symbols", {})
            if isinstance(symbols, dict) and symbol in symbols:
                return symbols[symbol].get("max_leverage")
            elif isinstance(symbols, list) and symbol in symbols:
                return market_config.get("max_leverage")  # Fallback for old format
        return None
    
    def snap_to_tick(self, price: float, symbol: str) -> float:
        """Snap price to valid tick size"""
        tick_size = self.get_tick_size(symbol)
        if tick_size is None:
            logger.warning(f"⚠️ No tick size found for symbol {symbol}, returning original price {price}")
            return price
        
        snapped_price = round(price / tick_size) * tick_size
        # Calculate decimal precision based on tick size
        # For tick_size 0.01, we need 2 decimals; for 0.001 we need 3, etc.
        if tick_size >= 1:
            decimals = 0
        else:
            # Count decimal places: log10(1/tick_size)
            decimals = max(0, -int(math.log10(tick_size)))

        snapped_price = round(snapped_price, decimals)
        
        logger.info(f"🔧 Price snapping: {price} / {tick_size} = {price / tick_size} → round = {round(price / tick_size)} → {snapped_price}")
        return snapped_price
    
    def snap_to_lot(self, quantity: float, symbol: str) -> float:
        """Snap quantity to valid lot size"""
        lot_size = self.get_lot_size(symbol)
        if lot_size is None:
            return quantity
        
        return round(quantity / lot_size) * lot_size
    
    def convert_quantity_to_broker_units(self, quantity: float, symbol: str) -> float:
        """Convert quantity to broker's expected base unit"""
        # Import here to avoid circular imports
        from ..config.brokers import BaseUnit
        
        if not hasattr(self.config, 'base_unit'):
            return quantity  # No conversion configured
        
        if self.config.base_unit == BaseUnit.CONTRACTS:
            # Convert from tokens to contracts using lot_size from market config
            # For DOGE_USDT: lot_size = 100 means 1 contract = 100 DOGE
            # So quantity_in_contracts = doge_quantity / lot_size
            lot_size = self.get_lot_size(symbol)
            if lot_size and lot_size > 0:
                return quantity / lot_size
            else:
                # Fallback to base_unit_conversion if lot_size not found
                conversion_factor = getattr(self.config, 'base_unit_conversion', {}).get(symbol, 1.0)
                return quantity / conversion_factor
        elif self.config.base_unit == BaseUnit.CURRENCY:
            # Convert from tokens to currency (e.g., USD value)
            # This would need price data to implement properly
            return quantity
        else:
            # BaseUnit.TOKENS - no conversion needed
            return quantity
    
    def convert_quantity_from_broker_units(self, quantity: float, symbol: str) -> float:
        """Convert quantity from broker's units back to base units"""
        # Import here to avoid circular imports
        from ..config.brokers import BaseUnit
        
        if not hasattr(self.config, 'base_unit'):
            return quantity  # No conversion configured
        
        if self.config.base_unit == BaseUnit.CONTRACTS:
            # Convert from contracts back to tokens using lot_size from market config
            # For DOGE_USDT: lot_size = 100 means 1 contract = 100 DOGE
            # So token_quantity = contract_quantity * lot_size
            lot_size = self.get_lot_size(symbol)
            if lot_size and lot_size > 0:
                return quantity * lot_size
            else:
                # Fallback to base_unit_conversion if lot_size not found
                conversion_factor = getattr(self.config, 'base_unit_conversion', {}).get(symbol, 1.0)
                return quantity * conversion_factor
        elif self.config.base_unit == BaseUnit.CURRENCY:
            # Convert from currency back to tokens (would need price data)
            return quantity
        else:
            # BaseUnit.TOKENS - no conversion needed
            return quantity
    
    def validate_order(self, order: OrderRequest) -> Dict[str, Any]:
        """Validate order against broker constraints"""
        errors = []
        warnings = []
        
        # Check symbol support
        symbol = order.instrument.symbol
        symbol_supported = False
        for market_type, market_config in self.config.markets.items():
            symbols = market_config.get("symbols", {})
            if isinstance(symbols, dict) and symbol in symbols:
                symbol_supported = True
                break
            elif isinstance(symbols, list) and symbol in symbols:
                symbol_supported = True
                break
        
        if not symbol_supported:
            errors.append(f"Symbol {symbol} not supported by {self.name}")
        
        # Check order size constraints
        if hasattr(order, 'quantity') and order.quantity:
            qty = order.quantity.value
            min_size = self.config.min_order_size
            max_size = self.config.max_order_size
            
            if min_size and qty < min_size:
                errors.append(f"Order size {qty} below minimum {min_size}")
            if max_size and qty > max_size:
                errors.append(f"Order size {qty} above maximum {max_size}")
        
        # Check feature support
        if order.flags.post_only and not self.supports_feature("supports_post_only"):
            errors.append(f"{self.name} does not support post-only orders")
        
        if order.order_type in ["STOP", "STOP_LIMIT"] and not self.supports_feature("supports_stop_loss"):
            errors.append(f"{self.name} does not support stop orders")
        
        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings
        }
