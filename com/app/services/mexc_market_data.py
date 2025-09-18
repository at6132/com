"""
MEXC Futures Market Data Service for COM Internal Use
COM needs this for order monitoring, fill confirmation, TP/SL management, and risk calculations
NOT exposed as API endpoints - purely internal service
"""
import asyncio
import json
import logging
from datetime import datetime
from typing import Dict, Any, Optional, Callable, List
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

@dataclass
class MarketData:
    """Real-time market data structure for COM internal use"""
    symbol: str
    bid: float
    ask: float
    last_price: float
    volume: float
    timestamp: datetime
    spread_bps: float = field(init=False)
    
    def __post_init__(self):
        if self.last_price > 0:
            self.spread_bps = ((self.ask - self.bid) / self.last_price) * 10000
        else:
            self.spread_bps = 0.0

@dataclass
class OrderBookLevel:
    """Order book level for COM internal use"""
    price: float
    quantity: float

@dataclass
class OrderBook:
    """Complete order book for COM internal use"""
    symbol: str
    timestamp: datetime
    bids: List[OrderBookLevel] = field(default_factory=list)
    asks: List[OrderBookLevel] = field(default_factory=list)
    
    def get_best_bid(self) -> Optional[float]:
        return self.bids[0].price if self.bids else None
    
    def get_best_ask(self) -> Optional[float]:
        return self.asks[0].price if self.asks else None
    
    def get_spread(self) -> Optional[float]:
        if self.get_best_bid() and self.get_best_ask():
            return self.get_best_ask() - self.get_best_bid()
        return None

class MEXCMarketDataService:
    """MEXC Futures REST API market data service for COM internal operations"""
    
    def __init__(self):
        # Connection state
        self._connected = False
        self._task = None
        
        # Market data storage for COM internal use
        self.market_data: Dict[str, MarketData] = {}
        self.order_books: Dict[str, OrderBook] = {}
        
        # Internal COM callbacks for order monitoring
        self._price_callbacks: List[Callable[[str, MarketData], None]] = []
        self._orderbook_callbacks: List[Callable[[str, OrderBook], None]] = []
        
        # Subscribed symbols (COM monitors these for order management)
        self._subscribed_symbols: set = set()
        
        logger.info("MEXC Market Data Service initialized for COM internal use")
    
    async def connect(self) -> bool:
        """Connect to MEXC Futures REST API for COM internal operations"""
        try:
            logger.info("Connecting to MEXC Futures REST API for COM internal use...")
            
            # For now, just mark as connected - we'll use REST API calls
            self._connected = True
            logger.info("✅ Connected to MEXC Futures REST API for COM internal operations")
            
            # Start data polling task
            self._task = asyncio.create_task(self._poll_market_data())
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to connect to MEXC REST API for COM: {e}")
            self._connected = False
            return False
    
    async def disconnect(self):
        """Disconnect from MEXC market data service"""
        self._connected = False
        
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        
        logger.info("Disconnected from MEXC market data service")
    
    async def subscribe_symbol(self, symbol: str) -> bool:
        """Subscribe to market data for COM order monitoring"""
        if not self._connected:
            logger.error("Not connected to MEXC market data service")
            return False
        
        try:
            # For REST API polling, just add to subscribed symbols
            # The polling task will automatically fetch data for all subscribed symbols
            self._subscribed_symbols.add(symbol)
            
            logger.info(f"✅ COM subscribed to {symbol} market data for internal monitoring")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to subscribe COM to {symbol}: {e}")
            return False
    
    async def unsubscribe_symbol(self, symbol: str) -> bool:
        """Unsubscribe from market data when COM no longer needs it"""
        if not self._connected:
            return False
        
        try:
            # For REST API polling, just remove from subscribed symbols
            # The polling task will automatically stop fetching data for unsubscribed symbols
            self._subscribed_symbols.discard(symbol)
            
            logger.info(f"COM unsubscribed from {symbol} market data")
            return True
            
        except Exception as e:
            logger.error(f"Failed to unsubscribe COM from {symbol}: {e}")
            return False
    
    async def _poll_market_data(self):
        """Poll MEXC Futures REST API for market data"""
        try:
            import aiohttp
            
            while self._connected:
                try:
                    # Poll each subscribed symbol (create a copy to avoid iteration issues)
                    subscribed_copy = self._subscribed_symbols.copy()
                    for symbol in subscribed_copy:
                        await self._fetch_symbol_data(symbol)
                    
                    # Wait before next poll
                    await asyncio.sleep(0.5)  # Poll every 0.5 seconds for faster monitoring
                    
                except Exception as e:
                    logger.error(f"Error polling market data: {e}")
                    await asyncio.sleep(1)  # Wait 1 second on error, then retry
                    
        except asyncio.CancelledError:
            logger.info("Market data polling task cancelled")
        except Exception as e:
            logger.error(f"Market data polling error: {e}")
        finally:
            self._connected = False
    
    async def _fetch_symbol_data(self, symbol: str):
        """Fetch market data for a specific symbol from MEXC Futures REST API"""
        try:
            import aiohttp
            
            # MEXC Futures ticker endpoint (same as your working script)
            url = f"https://contract.mexc.com/api/v1/contract/ticker?symbol={symbol}"
            
            timeout = aiohttp.ClientTimeout(total=5)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url, timeout=timeout) as response:
                    if response.status == 200:
                        data = await response.json()
                        
                        # Parse ticker data
                        ticker_data = data.get('data') or {}
                        bid1 = ticker_data.get('bid1')
                        ask1 = ticker_data.get('ask1')
                        last_price = ticker_data.get('last') or ticker_data.get('lastPrice') or ticker_data.get('price')
                        volume = ticker_data.get('volume', 0)
                        
                        if bid1 is not None and ask1 is not None:
                            # Update market data
                            if symbol not in self.market_data:
                                self.market_data[symbol] = MarketData(
                                    symbol=symbol,
                                    bid=float(bid1),
                                    ask=float(ask1),
                                    last_price=float(last_price) if last_price else 0.0,
                                    volume=float(volume),
                                    timestamp=datetime.utcnow()
                                )
                            else:
                                self.market_data[symbol].bid = float(bid1)
                                self.market_data[symbol].ask = float(ask1)
                                self.market_data[symbol].last_price = float(last_price) if last_price else 0.0
                                self.market_data[symbol].volume = float(volume)
                                self.market_data[symbol].timestamp = datetime.utcnow()
                            
                            # Update order book
                            if symbol not in self.order_books:
                                self.order_books[symbol] = OrderBook(
                                    symbol=symbol,
                                    timestamp=datetime.utcnow()
                                )
                            
                            orderbook = self.order_books[symbol]
                            orderbook.timestamp = datetime.utcnow()
                            orderbook.bids = [OrderBookLevel(price=float(bid1), quantity=0.0)]
                            orderbook.asks = [OrderBookLevel(price=float(ask1), quantity=0.0)]
                            
                            # Trigger callbacks
                            for callback in self._price_callbacks:
                                try:
                                    callback(symbol, self.market_data[symbol])
                                except Exception as e:
                                    logger.error(f"Price callback error: {e}")
                            
                            for callback in self._orderbook_callbacks:
                                try:
                                    callback(symbol, orderbook)
                                except Exception as e:
                                    logger.error(f"OrderBook callback error: {e}")
                            
                            logger.debug(f"Updated {symbol}: bid={bid1}, ask={ask1}, last={last_price}")
                        else:
                            logger.warning(f"No bid/ask data for {symbol}")
                    else:
                        logger.warning(f"Failed to fetch ticker for {symbol}: {response.status}")
                        
        except Exception as e:
            logger.error(f"Error fetching data for {symbol}: {e}")
    

    
    # Internal COM methods for order monitoring and management
    
    def get_market_data(self, symbol: str) -> Optional[MarketData]:
        """Get current market data for COM internal use (order monitoring, fill confirmation)"""
        return self.market_data.get(symbol)
    
    def get_order_book(self, symbol: str) -> Optional[OrderBook]:
        """Get current order book for COM internal use (order monitoring, TP/SL triggers)"""
        return self.order_books.get(symbol)
    
    def get_all_market_data(self) -> Dict[str, MarketData]:
        """Get all current market data for COM internal operations"""
        return self.market_data.copy()
    
    def add_price_callback(self, callback: Callable[[str, MarketData], None]):
        """Add callback for COM internal price updates (fill confirmation, TP/SL triggers)"""
        self._price_callbacks.append(callback)
    
    def add_orderbook_callback(self, callback: Callable[[str, OrderBook], None]):
        """Add callback for COM internal order book updates (order monitoring)"""
        self._orderbook_callbacks.append(callback)
    
    def is_connected(self) -> bool:
        """Check if connected to MEXC market data service for COM internal operations"""
        return self._connected
    
    def get_subscribed_symbols(self) -> set:
        """Get list of symbols COM is monitoring internally"""
        return self._subscribed_symbols.copy()
    
    def get_current_price(self, symbol: str) -> Optional[float]:
        """Get current price for COM internal use (TP/SL triggers, risk management)"""
        market_data = self.get_market_data(symbol)
        return market_data.last_price if market_data else None
    
    def get_best_bid_ask(self, symbol: str) -> tuple[Optional[float], Optional[float]]:
        """Get best bid/ask for COM internal use (order monitoring, fill confirmation)"""
        market_data = self.get_market_data(symbol)
        if market_data:
            return market_data.bid, market_data.ask
        return None, None

# Global market data service instance for COM internal use
mexc_market_data = MEXCMarketDataService()
