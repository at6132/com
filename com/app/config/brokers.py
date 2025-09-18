"""
Broker configuration system
Makes it easy to add new brokers one by one
"""
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field
from pathlib import Path
import yaml
from enum import Enum

class BaseUnit(str, Enum):
    CURRENCY = "currency"      # USD, USDT, etc.
    CONTRACTS = "contracts"    # Futures contracts
    TOKENS = "tokens"          # Crypto tokens, shares, etc.

class BrokerConfig(BaseModel):
    """Base broker configuration"""
    name: str
    enabled: bool = True
    environment: str = "live"  # live, paper, testnet
    api_key: Optional[str] = None
    secret_key: Optional[str] = None
    token: Optional[str] = None  # For MEXC and other token-based brokers
    passphrase: Optional[str] = None  # For some brokers like OKX
    base_url: str
    timeout: int = 30
    max_retries: int = 3
    rate_limit: Optional[Dict[str, Any]] = None
    
    # Base unit configuration
    base_unit: BaseUnit = BaseUnit.TOKENS  # Default to tokens
    base_unit_conversion: Dict[str, float] = Field(default_factory=dict)  # Symbol -> conversion factor
    
    # Broker-specific features
    features: Dict[str, Any] = Field(default_factory=dict)
    
    # Market configuration
    markets: Dict[str, Any] = Field(default_factory=dict)
    
    # Trading parameters
    min_order_size: Optional[float] = None
    max_order_size: Optional[float] = None
    tick_size: Optional[float] = None
    lot_size: Optional[float] = None
    contract_multiplier: Optional[float] = None
    
    class Config:
        extra = "allow"  # Allow broker-specific fields

class MEXCConfig(BrokerConfig):
    """MEXC-specific configuration"""
    testnet: bool = False
    futures: bool = True  # True for futures, False for spot
    
    # MEXC uses contracts as base unit
    base_unit: BaseUnit = BaseUnit.CONTRACTS
    base_unit_conversion: Dict[str, float] = {
        "BTC_USDT": 10000.0,  # 1 contract = 0.0001 BTC (1/0.0001)
        "ETH_USDT": 1000.0,   # 1 contract = 0.001 ETH (1/0.001)
    }
    
    # MEXC-specific features
    features: Dict[str, Any] = Field(default_factory=lambda: {
        "supports_stop_loss": True,
        "supports_take_profit": True,
        "supports_post_only": True,
        "supports_oco": False,
        "supports_trailing_stop": False,
        "unit_type": "contracts"  # contracts, base, quote
    })
    
    # MEXC market configuration
    markets: Dict[str, Any] = Field(default_factory=lambda: {
        "crypto_perp": {
            "symbols": {
                "BTC_USDT": {
                    "tick_size": 0.1,
                    "lot_size": 0.001,
                    "contract_multiplier": 1,
                    "min_order_size": 0.001,
                    "max_order_size": 1000000,
                    "min_notional": 5.0,
                    "max_leverage": 125
                },
                "ETH_USDT": {
                    "tick_size": 0.01,
                    "lot_size": 0.01,
                    "contract_multiplier": 1,
                    "min_order_size": 0.01,
                    "max_order_size": 1000000,
                    "min_notional": 5.0,
                    "max_leverage": 125
                }
            }
        }
    })

class BrokerRegistry:
    """Registry for all broker configurations"""
    
    def __init__(self, config_dir: str = "config/brokers"):
        self.config_dir = Path(config_dir)
        self.brokers: Dict[str, BrokerConfig] = {}
        self._load_configs()
    
    def _load_configs(self):
        """Load broker configurations from YAML files"""
        if not self.config_dir.exists():
            self.config_dir.mkdir(parents=True, exist_ok=True)
            self._create_default_configs()
            return
        
        for config_file in self.config_dir.glob("*.yaml"):
            broker_name = config_file.stem
            try:
                with open(config_file, 'r') as f:
                    config_data = yaml.safe_load(f)
                
                if broker_name == "mexc":
                    self.brokers[broker_name] = MEXCConfig(**config_data)
                else:
                    self.brokers[broker_name] = BrokerConfig(**config_data)
                    
                print(f"Loaded broker config: {broker_name}")
            except Exception as e:
                print(f"Error loading broker config {broker_name}: {e}")
    
    def _create_default_configs(self):
        """Create default broker configuration files"""
        # MEXC default config
        mexc_config = MEXCConfig(
            name="MEXC",
            enabled=True,
            environment="paper",
            base_url="https://api.mexc.com",
            testnet=True,
            futures=True
        )
        
        mexc_file = self.config_dir / "mexc.yaml"
        with open(mexc_file, 'w') as f:
            yaml.dump(mexc_config.model_dump(), f, default_flow_style=False)
        
        print(f"Created default MEXC config: {mexc_file}")
    
    def get_broker(self, name: str) -> Optional[BrokerConfig]:
        """Get broker configuration by name"""
        return self.brokers.get(name)
    
    def get_enabled_brokers(self) -> Dict[str, BrokerConfig]:
        """Get all enabled brokers"""
        return {name: config for name, config in self.brokers.items() if config.enabled}
    
    def list_brokers(self) -> list[str]:
        """List all configured broker names"""
        return list(self.brokers.keys())
    
    def reload_configs(self):
        """Reload broker configurations"""
        self.brokers.clear()
        self._load_configs()

# Global broker registry instance
broker_registry = BrokerRegistry()
