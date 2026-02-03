"""
WebSocket Feed Manager for Polymarket Arbitrage Bot

Manages real-time data feeds from:
1. Polymarket CLOB (order book updates)
2. Binance (BTC price)
"""
import asyncio
import websockets
import json
import time
from typing import Dict, Callable, Optional
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class PolymarketWebSocket:
    """Real-time order book feed for btc-updown-15m markets"""
    
    def __init__(self, market_id: str, on_update: Callable):
        self.market_id = market_id
        self.on_update = on_update
        self.ws = None
        self.running = False
        
        # Order book state
        self.order_book = {
            "up_bids": [],
            "up_asks": [],
            "down_bids": [],
            "down_asks": []
        }
        
    async def connect(self):
        """Connect to Polymarket WebSocket"""
        url = f"wss://ws-subscriptions-clob.polymarket.com/ws/market"
        
        try:
            self.ws = await websockets.connect(url)
            logger.info(f"Connected to Polymarket WebSocket for {self.market_id}")
            
            # Subscribe to market
            subscribe_msg = {
                "type": "subscribe",
                "market": self.market_id
            }
            await self.ws.send(json.dumps(subscribe_msg))
            self.running = True
            
        except Exception as e:
            logger.error(f"Failed to connect to Polymarket WS: {e}")
            raise
    
    async def listen(self):
        """Listen for order book updates"""
        try:
            async for message in self.ws:
                if not self.running:
                    break
                    
                data = json.loads(message)
                
                # Process order book update
                if data.get("type") == "book_update":
                    self._update_order_book(data)
                    
                    # Notify callback
                    await self.on_update({
                        "market_id": self.market_id,
                        "order_book": self.order_book,
                        "timestamp": time.time()
                    })
                    
        except websockets.exceptions.ConnectionClosed:
            logger.warning("Polymarket WebSocket connection closed")
            if self.running:
                await self.reconnect()
        except Exception as e:
            logger.error(f"Error in Polymarket WS listen: {e}")
            
    def _update_order_book(self, data: Dict):
        """Update internal order book state"""
        # Implementation depends on Polymarket's actual WebSocket format
        # This is a placeholder structure
        side = data.get("side")  # "up" or "down"
        asks = data.get("asks", [])
        bids = data.get("bids", [])
        
        if side == "up":
            self.order_book["up_asks"] = asks
            self.order_book["up_bids"] = bids
        elif side == "down":
            self.order_book["down_asks"] = asks
            self.order_book["down_bids"] = bids
    
    async def reconnect(self):
        """Reconnect to WebSocket"""
        logger.info("Reconnecting to Polymarket WebSocket...")
        await asyncio.sleep(2)
        await self.connect()
        await self.listen()
    
    async def close(self):
        """Close WebSocket connection"""
        self.running = False
        if self.ws:
            await self.ws.close()


class BinanceWebSocket:
    """Real-time BTC price feed from Binance"""
    
    def __init__(self, on_update: Callable):
        self.on_update = on_update
        self.ws = None
        self.running = False
        
        # Price tracking
        self.current_price = None
        self.price_history = []  # Last 60 seconds
        
    async def connect(self):
        """Connect to Binance WebSocket"""
        url = "wss://stream.binance.com:9443/ws/btcusdt@trade"
        
        try:
            self.ws = await websockets.connect(url)
            logger.info("Connected to Binance WebSocket (BTC/USDT)")
            self.running = True
            
        except Exception as e:
            logger.error(f"Failed to connect to Binance WS: {e}")
            raise
    
    async def listen(self):
        """Listen for BTC price updates"""
        try:
            async for message in self.ws:
                if not self.running:
                    break
                    
                data = json.loads(message)
                price = float(data.get("p", 0))
                timestamp = data.get("T", time.time())
                
                # Update price
                self.current_price = price
                self.price_history.append({
                    "price": price,
                    "timestamp": timestamp / 1000  # Convert to seconds
                })
                
                # Keep only last 60 seconds
                cutoff = (timestamp / 1000) - 60
                self.price_history = [
                    p for p in self.price_history 
                    if p["timestamp"] > cutoff
                ]
                
                # Calculate momentum (% change in last 5 seconds)
                momentum_5s = self._calculate_momentum(5)
                momentum_10s = self._calculate_momentum(10)
                
                # Notify callback
                await self.on_update({
                    "price": price,
                    "momentum_5s": momentum_5s,
                    "momentum_10s": momentum_10s,
                    "timestamp": timestamp / 1000
                })
                    
        except websockets.exceptions.ConnectionClosed:
            logger.warning("Binance WebSocket connection closed")
            if self.running:
                await self.reconnect()
        except Exception as e:
            logger.error(f"Error in Binance WS listen: {e}")
    
    def _calculate_momentum(self, seconds: int) -> float:
        """Calculate % price change over last N seconds"""
        if len(self.price_history) < 2:
            return 0.0
        
        current_time = time.time()
        cutoff = current_time - seconds
        
        # Get prices from N seconds ago
        old_prices = [p for p in self.price_history if p["timestamp"] <= cutoff]
        if not old_prices:
            return 0.0
            
        old_price = old_prices[-1]["price"]
        current_price = self.current_price
        
        momentum = ((current_price - old_price) / old_price) * 100
        return round(momentum, 2)
    
    async def reconnect(self):
        """Reconnect to WebSocket"""
        logger.info("Reconnecting to Binance WebSocket...")
        await asyncio.sleep(2)
        await self.connect()
        await self.listen()
    
    async def close(self):
        """Close WebSocket connection"""
        self.running = False
        if self.ws:
            await self.ws.close()


class FeedManager:
    """Manages all WebSocket feeds and aggregates data"""
    
    def __init__(self, market_id: str, on_data: Callable):
        self.market_id = market_id
        self.on_data = on_data
        
        self.poly_ws = PolymarketWebSocket(market_id, self._on_poly_update)
        self.binance_ws = BinanceWebSocket(self._on_binance_update)
        
        # Aggregated state
        self.state = {
            "market_id": market_id,
            "order_book": None,
            "btc_price": None,
            "btc_momentum_5s": 0.0,
            "btc_momentum_10s": 0.0,
            "last_update": None
        }
        
    async def _on_poly_update(self, data: Dict):
        """Handle Polymarket update"""
        self.state["order_book"] = data.get("order_book")
        self.state["last_update"] = time.time()
        await self._notify()
    
    async def _on_binance_update(self, data: Dict):
        """Handle Binance update"""
        self.state["btc_price"] = data.get("price")
        self.state["btc_momentum_5s"] = data.get("momentum_5s")
        self.state["btc_momentum_10s"] = data.get("momentum_10s")
        await self._notify()
    
    async def _notify(self):
        """Notify main callback with aggregated state"""
        if self.state["order_book"] and self.state["btc_price"]:
            await self.on_data(self.state)
    
    async def start(self):
        """Start all WebSocket feeds"""
        logger.info(f"Starting feeds for {self.market_id}")
        
        # Connect
        await self.poly_ws.connect()
        await self.binance_ws.connect()
        
        # Listen in parallel
        await asyncio.gather(
            self.poly_ws.listen(),
            self.binance_ws.listen()
        )
    
    async def stop(self):
        """Stop all feeds"""
        logger.info("Stopping feeds...")
        await self.poly_ws.close()
        await self.binance_ws.close()


# Example usage
async def main():
    """Test the WebSocket feeds"""
    
    async def on_data(state):
        logger.info(f"Got data update:")
        logger.info(f"  BTC Price: ${state['btc_price']:.2f}")
        logger.info(f"  Momentum (5s): {state['btc_momentum_5s']}%")
        logger.info(f"  Order Book: {len(state['order_book']['up_asks'])} levels")
    
    # Get active market ID
    import datetime
    now = datetime.datetime.now(datetime.timezone.utc)
    base = now.replace(second=0, microsecond=0)
    minutes_to_remove = base.minute % 15
    current_mark = base - datetime.timedelta(minutes=minutes_to_remove)
    ts = int(current_mark.timestamp())
    market_id = f"btc-updown-15m-{ts}"
    
    manager = FeedManager(market_id, on_data)
    
    try:
        await manager.start()
    except KeyboardInterrupt:
        await manager.stop()


if __name__ == "__main__":
    asyncio.run(main())
