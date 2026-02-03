
import logging
from typing import Optional, Dict
from py_clob_client.client import ClobClient

logger = logging.getLogger(__name__)

class MarketFinder:
    """Finds active markets for arbitrage"""
    
    def __init__(self, client: ClobClient):
        self.client = client
        
    def find_active_btc_market(self) -> Optional[Dict]:
        """
        Finds the current active 15min BTC market.
        Returns:
            Dict containing market_id, token_ids, and other metadata
            or None if no suitable market found
        """
        try:
            # We want headers for pagination if needed, but for now just get first page
            # Gamma (markets) API is usually available via ClobClient
            
            # Use filters to find active BTC markets
            # Note: py-clob-client uses 'get_markets' which hits the Gamma API
            # Corrected for py-clob-client v0.34.5
            # get_markets generally takes a list of params or uses a specific pagination method
            # If arguments are invalid, we should try using kwargs not explicitly defined in some versions
            # However, looking at source, newer versions might use `next_cursor` or similar.
            # Safest fix: Pass only arguments we are sure of, or handle pagination differently.
            # Assuming `active` and `closed` are valid filters in the params dict or args.
            
            # Trying minimal arguments to fix TypeError
            markets = self.client.get_markets(
                active=True,
                closed=False
            )
            
            # Filter logic:
            # 1. Must be "Bitcoin > $X" or similar 15min binary market
            # 2. Must be OPEN
            # 3. Choose the one expiring soonest but still tradable? 
            #    Or starting soonest?
            #    Usually "active" means currently trading.
            
            # Since we are looking for "BTC Prices", let's look for the tag or description
            # The simplified logic: Find market ID start with "btc-updown-15m"?
            # Actually, standard Polymarket naming is complex. 
            # We look for "Bitcoin" and "15min" in question or description?
            
            # Assuming we can filter by 'tag' or search in client, but client.get_markets is limited.
            # Let's iterate and find best match.
            
            # Best way: Look for markets with 'Bitcoin' in question
            
            for m in markets:
                # Basic check for BTC 15m binary market
                # This logic is approximate and might need refinement based on exact Polymarket API response
                if "Bitcoin" in m.get("question", "") and "15m" in m.get("slug", ""):
                     if m.get("active") and not m.get("closed"):
                         # Found one!
                         logger.info(f"Found active market: {m.get('question')} ({m.get('condition_id')})")
                         
                         # Extract token IDs
                         tokens = m.get("tokens", [])
                         if len(tokens) >= 2:
                             return {
                                 "market_id": m.get("condition_id"),
                                 "question": m.get("question"),
                                 "up_token_id": tokens[0]["token_id"],
                                 "down_token_id": tokens[1]["token_id"],
                                 "end_date_iso": m.get("end_date_iso")
                             }
                             
            logger.warning("No active BTC 15m market found in recent list")
            return None
            
        except Exception as e:
            logger.error(f"Error finding market: {e}")
            return None
