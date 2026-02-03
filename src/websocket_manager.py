
import asyncio
import json
import logging
from typing import Dict, List, Optional
import websockets

logger = logging.getLogger(__name__)

class OrderBook:
    """Maintains local order book state"""
    def __init__(self):
        self.bids: Dict[float, float] = {}
        self.asks: Dict[float, float] = {}
        self.market_id = None
        self.last_update = 0

    def update(self, side: str, price: float, size: float):
        """Update a price level"""
        # Price is key, Size is value
        # If size is 0, remove level
        target = self.bids if side == "BUY" else self.asks
        
        if float(size) == 0:
            if price in target:
                del target[price]
        else:
            target[price] = float(size)

    def get_snapshot(self) -> Dict:
        """Get sorted snapshot for arbitrage engine"""
        # Sort asks ascending (cheapest first)
        # Sort bids descending (highest first)
        
        sorted_asks = sorted(self.asks.items(), key=lambda x: float(x[0]))
        sorted_bids = sorted(self.bids.items(), key=lambda x: float(x[0]), reverse=True)
        
        return {
            "asks": [{"price": float(p), "size": float(s)} for p, s in sorted_asks],
            "bids": [{"price": float(p), "size": float(s)} for p, s in sorted_bids]
        }

class WebSocketManager:
    """Manages WebSocket connection to Polymarket CLOB"""
    
    def __init__(self, ws_url: str = "wss://ws-subscriptions-clob.polymarket.com/ws/market"):
        self.ws_url = ws_url
        self.ws = None
        self.running = False
        self.market_id = None
        self.token_ids = []
        self.order_books: Dict[str, OrderBook] = {} # token_id -> OrderBook
        
    async def connect(self):
        """Connect to WebSocket"""
        try:
            self.ws = await websockets.connect(self.ws_url)
            logger.info("Connected to Polymarket WebSocket")
            self.running = True
            
            # Start listener loop
            asyncio.create_task(self._listen())
            
            # Subscribe if we already have tokens
            if self.token_ids:
                await self.subscribe(self.token_ids)
                
        except Exception as e:
            logger.error(f"WebSocket connection failed: {e}")
            self.running = False

    async def subscribe(self, token_ids: List[str]):
        """Subscribe to order book updates for tokens"""
        self.token_ids = token_ids
        
        # Initialize order books
        for tid in token_ids:
            if tid not in self.order_books:
                self.order_books[tid] = OrderBook()
        
        if not self.ws or not self.running:
            return

        # Prepare subscription message
        # Format: {"type": "Market", "assets_ids": ["..."], "timestamp": ...}
        # Note: Polymarket WS protocol specifics
        msg = {
            "assets_ids": token_ids,
            "type": "market" 
        }
        
        await self.ws.send(json.dumps(msg))
        logger.info(f"Subscribed to {len(token_ids)} assets")

    async def _listen(self):
        """Listen for messages"""
        while self.running and self.ws:
            try:
                msg = await self.ws.recv()
                data = json.loads(msg)
                
                # Handle order book updates
                # Expected format needs to be confirmed with API docs
                # Usually: event_type: "book", asset_id: "...", bids: [], asks: []
                
                for item in data:
                    if item.get("event_type") == "book":
                        asset_id = item.get("asset_id")
                        if asset_id in self.order_books:
                            book = self.order_books[asset_id]
                            
                            # Updates are usually list of {price, size}
                            for bid in item.get("bids", []):
                                book.update("BUY", bid["price"], bid["size"])
                            
                            for ask in item.get("asks", []):
                                book.update("SELL", ask["price"], ask["size"])
                                
            except websockets.ConnectionClosed:
                logger.warning("WebSocket connection closed, reconnecting...")
                await asyncio.sleep(1)
                await self.connect()
                break
            except Exception as e:
                logger.error(f"WebSocket error: {e}")
                await asyncio.sleep(1)

    def get_order_book(self, token_id: str) -> Optional[Dict]:
        """Get snapshot for a specific token"""
        if token_id in self.order_books:
            return self.order_books[token_id].get_snapshot()
        return None
