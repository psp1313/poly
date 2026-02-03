"""
Chainlink Price Feed Integration

Fetches real-time BTC/USD price from Chainlink's settlement oracle.
This is the SAME price Polymarket uses to settle btc-updown-15m markets.

Methods:
1. On-chain: Read from Chainlink oracle contract on Polygon
2. API: Use Chainlink Data Streams API (faster, off-chain)

For speed, we'll use the Data Streams API with on-chain verification.
"""
import aiohttp
import logging
from typing import Optional, Dict
from web3 import Web3
import time

logger = logging.getLogger(__name__)


class ChainlinkPriceFeed:
    """
    Fetch BTC/USD price from Chainlink
    
    Uses Chainlink Data Streams for low-latency updates,
    with on-chain oracle as fallback/verification.
    """
    
    # Chainlink BTC/USD feed on Polygon
    CHAINLINK_BTC_USD_POLYGON = "0xc907E116054Ad103354f2D350FD2514433D57F6f"
    
    # Data Streams API (if available)
    DATA_STREAMS_URL = "https://api.chain.link/v1/streams/btc-usd"
    
    def __init__(self, polygon_rpc_list: list = None):
        if polygon_rpc_list is None:
            self.rpcs = [
                "https://polygon-bor-rpc.publicnode.com",
                "https://polygon.drpc.org",
                "https://polygon-rpc.com"
            ]
        else:
            self.rpcs = polygon_rpc_list
            
        self.current_rpc_index = 0
        self.w3 = Web3(Web3.HTTPProvider(self.rpcs[0]))
        
        # Chainlink aggregator ABI (minimal)
        self.aggregator_abi = [
            {
                "inputs": [],
                "name": "latestRoundData",
                "outputs": [
                    {"name": "roundId", "type": "uint80"},
                    {"name": "answer", "type": "int256"},
                    {"name": "startedAt", "type": "uint256"},
                    {"name": "updatedAt", "type": "uint256"},
                    {"name": "answeredInRound", "type": "uint80"}
                ],
                "stateMutability": "view",
                "type": "function"
            },
            {
                "inputs": [],
                "name": "decimals",
                "outputs": [{"name": "", "type": "uint8"}],
                "stateMutability": "view",
                "type": "function"
            }
        ]
        
        self.contract = self.w3.eth.contract(
            address=Web3.to_checksum_address(self.CHAINLINK_BTC_USD_POLYGON),
            abi=self.aggregator_abi
        )
        
        # Cache
        self.last_price = None
        self.last_update = 0
        self.cache_duration = 1  # Cache for 1 second max
        
        logger.info("Chainlink price feed initialized (Polygon)")
    
    async def get_btc_price(self) -> Optional[float]:
        """
        Get current BTC/USD price from Chainlink
        
        Returns:
            BTC price in USD (e.g., 76500.00) or None on error
        """
        # Check cache
        if time.time() - self.last_update < self.cache_duration and self.last_price:
            return self.last_price
        
        try:
            # Method 1: Try Data Streams API first (faster)
            price = await self._get_from_data_streams()
            
            if price is None:
                # Method 2: Fallback to on-chain oracle
                price = await self._get_from_onchain()
            
            if price:
                self.last_price = price
                self.last_update = time.time()
                return price
            
            return None
            
        except Exception as e:
            logger.error(f"Error fetching Chainlink price: {e}")
            return self.last_price  # Return cached price on error
    
    async def _get_from_data_streams(self) -> Optional[float]:
        """
        Attempt to get price from Chainlink Data Streams API
        (This is a placeholder - actual API may require authentication)
        """
        try:
            # Note: This URL/API structure is hypothetical
            # Actual implementation may differ
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    self.DATA_STREAMS_URL,
                    timeout=aiohttp.ClientTimeout(total=2)
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        price = float(data.get("price", 0))
                        if price > 0:
                            logger.debug(f"Chainlink Data Streams: ${price:.2f}")
                            return price
        except Exception as e:
            logger.debug(f"Data Streams unavailable: {e}")
        
        return None
    
    async def _get_from_onchain(self) -> Optional[float]:
        """
        Get price from on-chain Chainlink oracle
        """
        try:
            # Call latestRoundData
            round_data = self.contract.functions.latestRoundData().call()
            
            # Extract price (answer)
            answer = round_data[1]
            
            # Get decimals
            decimals = self.contract.functions.decimals().call()
            
            # Convert to float
            price = float(answer) / (10 ** decimals)
            
            logger.debug(f"Chainlink On-Chain: ${price:.2f}")
            return price
            
        except Exception as e:
            logger.error(f"On-chain oracle error: {e}")
            # Rotate RPC on error
            self._rotate_rpc()
            return None

    def _rotate_rpc(self):
        """Switch to next RPC in list"""
        self.current_rpc_index = (self.current_rpc_index + 1) % len(self.rpcs)
        new_rpc = self.rpcs[self.current_rpc_index]
        logger.info(f"Rotating to RPC: {new_rpc}")
        self.w3 = Web3(Web3.HTTPProvider(new_rpc))
        
        # Re-initialize contract
        self.contract = self.w3.eth.contract(
            address=Web3.to_checksum_address(self.CHAINLINK_BTC_USD_POLYGON),
            abi=self.aggregator_abi
        )
    
    async def get_price_at_timestamp(self, timestamp: int) -> Optional[float]:
        """
        Get historical BTC price at specific timestamp
        (For verifying start price of 15-min interval)
        
        This would require historical data access or round lookup.
        For now, returns current price as approximation.
        """
        # TODO: Implement historical price lookup via Chainlink rounds
        # For MVP, we'll track start price manually
        return await self.get_btc_price()


# Simple HTTP fallback (Binance as backup)
class BinancePriceFeed:
    """Backup price feed using Binance API"""
    
    async def get_btc_price(self) -> Optional[float]:
        """Get BTC price from Binance"""
        try:
            url = "https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT"
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=2)) as response:
                    if response.status == 200:
                        data = await response.json()
                        price = float(data.get("price", 0))
                        return price
        except Exception as e:
            logger.error(f"Binance price fetch error: {e}")
            return None


# Unified price manager
class PriceOracle:
    """
    Unified price oracle with multiple sources
    
    Priority:
    1. Chainlink (primary - settlement oracle)
    2. Binance (backup)
    """
    
    def __init__(self):
        self.chainlink = ChainlinkPriceFeed()
        self.binance = BinancePriceFeed()
        logger.info("Price Oracle initialized")
    
    async def get_btc_price(self) -> Dict[str, float]:
        """
        Get BTC price from all sources
        
        Returns:
            {
                "chainlink": 76500.00,
                "binance": 76501.50,
                "settlement": 76500.00  # What Polymarket will use
            }
        """
        chainlink_price = await self.chainlink.get_btc_price()
        binance_price = await self.binance.get_btc_price()
        
        return {
            "chainlink": chainlink_price,
            "binance": binance_price,
            "settlement": chainlink_price  # Chainlink IS the settlement
        }


# Test
if __name__ == "__main__":
    import asyncio
    logging.basicConfig(level=logging.INFO)
    
    async def test():
        oracle = PriceOracle()
        prices = await oracle.get_btc_price()
        
        print("\n=== BTC Price Sources ===")
        print(f"Chainlink (Settlement): ${prices['chainlink']:.2f}")
        print(f"Binance (Reference):    ${prices['binance']:.2f}")
        
        if prices['chainlink'] and prices['binance']:
            diff = abs(prices['chainlink'] - prices['binance'])
            print(f"Difference: ${diff:.2f}")
    
    asyncio.run(test())
