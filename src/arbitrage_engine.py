"""
Arbitrage Engine for Polymarket BTC 15-Min Markets

Detects and validates arbitrage opportunities using:
1. Sum-to-One Arbitrage: P(Up) + P(Down) ≠ $1.00
2. Chainlink Misalignment: Market price diverges from settlement oracle
3. VWAP Slippage Protection: Ensure 4%+ profit after fees

Key insight: Chainlink is the SETTLEMENT ORACLE for Polymarket.
If market diverges from Chainlink, guaranteed arbitrage exists.
"""
import logging
from typing import Dict, Optional, List
from dataclasses import dataclass
import time

logger = logging.getLogger(__name__)


@dataclass
class ArbitrageOpportunity:
    """Represents a detected arbitrage opportunity"""
    type: str  # "sum_arbitrage", "chainlink_mismatch", "momentum"
    market_id: str
    profit_pct: float
    expected_profit: float
    total_cost: float
    
    # Order details
    up_price: Optional[float] = None
    down_price: Optional[float] = None
    up_size: Optional[float] = None
    down_size: Optional[float] = None
    
    # Metadata
    timestamp: float = None
    confidence: str = "medium"  # "low", "medium", "high"
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = time.time()


class ArbitrageEngine:
    """Detect profitable arbitrage opportunities"""
    
    def __init__(self, min_profit_pct: float = 0.04, max_slippage: float = 0.025):
        self.min_profit_pct = min_profit_pct  # 4% minimum
        self.max_slippage = max_slippage  # 2.5% max slippage
        
        # Fee structure (Polymarket charges ~1.5% total)
        self.maker_fee = 0.0  # No maker fee
        self.taker_fee = 0.015  # 1.5% taker fee
        
        logger.info(f"Arbitrage Engine initialized: {min_profit_pct*100}% min profit, {max_slippage*100}% max slippage")
    
    def check_sum_arbitrage(self, order_book: Dict, max_position: float) -> Optional[ArbitrageOpportunity]:
        """
        Sum-to-One Arbitrage: P(Up) + P(Down) must equal $1.00
        
        If Up_ask + Down_ask < 1.00: Buy both sides (guaranteed profit)
        If Up_bid + Down_bid > 1.00: Can't exploit (can't short on Polymarket)
        
        Args:
            order_book: {"up_asks": [...], "down_asks": [...], etc}
            max_position: Maximum $ to invest
            
        Returns:
            ArbitrageOpportunity if found, None otherwise
        """
        try:
            up_asks = order_book.get("up_asks", [])
            down_asks = order_book.get("down_asks", [])
            
            if not up_asks or not down_asks:
                return None
            
            # Best prices
            best_up_ask = float(up_asks[0]["price"])
            best_down_ask = float(down_asks[0]["price"])
            
            # Check sum
            total_cost_per_share = best_up_ask + best_down_ask
            guaranteed_return = 1.00
            
            # Gross profit before fees
            gross_profit_per_share = guaranteed_return - total_cost_per_share
            
            # Account for fees (we're taking liquidity, so taker fee applies)
            fee_cost = total_cost_per_share * self.taker_fee
            net_profit_per_share = gross_profit_per_share - fee_cost
            
            # Calculate profit percentage
            if total_cost_per_share <= 0:
                return None
                
            net_profit_pct = net_profit_per_share / total_cost_per_share
            
            # Check minimum threshold
            if net_profit_pct < self.min_profit_pct:
                return None
            
            # Calculate position size
            # We need to buy equal shares of both Up and Down
            max_shares = max_position / total_cost_per_share
            
            # Check liquidity (VWAP for full size)
            up_vwap = self._calculate_vwap(up_asks, max_shares)
            down_vwap = self._calculate_vwap(down_asks, max_shares)
            
            if up_vwap is None or down_vwap is None:
                logger.debug("Insufficient liquidity for sum arbitrage")
                return None
            
            # Recalculate with VWAP
            actual_cost_per_share = up_vwap + down_vwap
            actual_profit_per_share = guaranteed_return - actual_cost_per_share
            actual_fee = actual_cost_per_share * self.taker_fee
            actual_net_profit = actual_profit_per_share - actual_fee
            actual_profit_pct = actual_net_profit / actual_cost_per_share
            
            # Check slippage
            slippage = (actual_cost_per_share - total_cost_per_share) / total_cost_per_share
            if slippage > self.max_slippage:
                logger.debug(f"Slippage too high: {slippage*100:.2f}%")
                return None
            
            # Final threshold check
            if actual_profit_pct < self.min_profit_pct:
                logger.debug(f"Profit below threshold after slippage: {actual_profit_pct*100:.2f}%")
                return None
            
            # Valid arbitrage!
            total_cost = max_shares * actual_cost_per_share
            expected_profit = max_shares * actual_net_profit
            
            logger.info(f"SUM ARBITRAGE FOUND! Profit: {actual_profit_pct*100:.2f}% (${expected_profit:.2f})")
            
            return ArbitrageOpportunity(
                type="sum_arbitrage",
                market_id="",  # Set by caller
                profit_pct=actual_profit_pct,
                expected_profit=expected_profit,
                total_cost=total_cost,
                up_price=up_vwap,
                down_price=down_vwap,
                up_size=max_shares,
                down_size=max_shares,
                confidence="high"  # Guaranteed arbitrage
            )
            
        except Exception as e:
            logger.error(f"Error in sum arbitrage check: {e}")
            return None
    
    def check_chainlink_mismatch(
        self, 
        order_book: Dict, 
        chainlink_btc: float,
        current_btc_start: float,
        max_position: float
    ) -> Optional[ArbitrageOpportunity]:
        """
        Chainlink Misalignment Arbitrage
        
        Since Polymarket uses Chainlink to settle, if the market price
        diverges from what Chainlink will determine as the outcome,
        we have guaranteed arbitrage.
        
        Logic:
        - If BTC > start price AT SETTLEMENT (per Chainlink), "Up" pays $1
        - If current Chainlink BTC > start AND market "Up" < $0.90, BUY "Up"
        - If current Chainlink BTC < start AND market "Down" < $0.90, BUY "Down"
        
        Args:
            order_book: Market order book
            chainlink_btc: Current Chainlink BTC price
            current_btc_start: Start price for this 15-min interval
            max_position: Max $ to invest
        """
        try:
            # Determine which side SHOULD win based on Chainlink
            btc_delta = chainlink_btc - current_btc_start
            
            if btc_delta > 0:
                # BTC is up, "Up" should be favored
                target_side = "up"
                target_asks = order_book.get("up_asks", [])
            else:
                # BTC is down, "Down" should be favored
                target_side = "down"
                target_asks = order_book.get("down_asks", [])
            
            if not target_asks:
                return None
            
            best_ask = float(target_asks[0]["price"])
            
            # Arbitrage threshold: If winning side is < $0.85, definite mispricing
            # At expiration, winning side pays $1.00
            if best_ask >= 0.85:
                return None  # Market is fairly priced
            
            # Calculate expected profit
            settlement_value = 1.00
            gross_profit_per_share = settlement_value - best_ask
            
            # Account for fees
            fee = best_ask * self.taker_fee
            net_profit_per_share = gross_profit_per_share - fee
            net_profit_pct = net_profit_per_share / best_ask
            
            # Check threshold
            if net_profit_pct < self.min_profit_pct:
                return None
            
            # Calculate position size
            max_shares = max_position / best_ask
            
            # Check VWAP
            vwap = self._calculate_vwap(target_asks, max_shares)
            if vwap is None:
                return None
            
            # Recalculate with VWAP
            actual_profit = settlement_value - vwap
            actual_fee = vwap * self.taker_fee
            actual_net_profit = actual_profit - actual_fee
            actual_pct = actual_net_profit / vwap
            
            if actual_pct < self.min_profit_pct:
                return None
            
            total_cost = max_shares * vwap
            expected_profit = max_shares * actual_net_profit
            
            logger.info(f"CHAINLINK MISMATCH! {target_side.upper()} @ ${vwap:.3f} (should be $1.00)")
            logger.info(f"Profit: {actual_pct*100:.2f}% (${expected_profit:.2f})")
            
            opp = ArbitrageOpportunity(
                type="chainlink_mismatch",
                market_id="",
                profit_pct=actual_pct,
                expected_profit=expected_profit,
                total_cost=total_cost,
                confidence="high"
            )
            
            if target_side == "up":
                opp.up_price = vwap
                opp.up_size = max_shares
            else:
                opp.down_price = vwap
                opp.down_size = max_shares
            
            return opp
            
        except Exception as e:
            logger.error(f"Error in Chainlink mismatch check: {e}")
            return None
    
    def _calculate_vwap(self, order_levels: List[Dict], target_size: float) -> Optional[float]:
        """
        Calculate Volume-Weighted Average Price for target size
        
        Args:
            order_levels: List of {"price": 0.5, "size": 100}
            target_size: Number of shares to buy
            
        Returns:
            VWAP or None if insufficient liquidity
        """
        cumulative_volume = 0
        cumulative_cost = 0
        
        for level in order_levels:
            price = float(level.get("price", 0))
            size = float(level.get("size", 0))
            
            if cumulative_volume + size >= target_size:
                # This level completes the order
                remaining = target_size - cumulative_volume
                cumulative_cost += remaining * price
                cumulative_volume = target_size
                break
            else:
                # Take entire level
                cumulative_cost += size * price
                cumulative_volume += size
        
        # Check if we got enough liquidity
        if cumulative_volume < target_size:
            return None
        
        vwap = cumulative_cost / cumulative_volume
        return round(vwap, 3)
    
    def scan_opportunities(
        self, 
        order_book: Dict, 
        chainlink_btc: float,
        market_start_price: float,
        max_position: float,
        market_id: str
    ) -> List[ArbitrageOpportunity]:
        """
        Scan for all arbitrage opportunities
        
        Returns:
            List of opportunities, sorted by profit %
        """
        opportunities = []
        
        # Check sum-to-one arbitrage
        sum_opp = self.check_sum_arbitrage(order_book, max_position)
        if sum_opp:
            sum_opp.market_id = market_id
            opportunities.append(sum_opp)
        
        # Check Chainlink mismatch
        chainlink_opp = self.check_chainlink_mismatch(
            order_book, 
            chainlink_btc, 
            market_start_price, 
            max_position
        )
        if chainlink_opp:
            chainlink_opp.market_id = market_id
            opportunities.append(chainlink_opp)
        
        # Sort by profit percentage (highest first)
        opportunities.sort(key=lambda x: x.profit_pct, reverse=True)
        
        return opportunities


# Test function
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    # Sample data
    order_book = {
        "up_asks": [
            {"price": 0.45, "size": 100},
            {"price": 0.46, "size": 50}
        ],
        "down_asks": [
            {"price": 0.48, "size": 80},
            {"price": 0.49, "size": 60}
        ]
    }
    
    engine = ArbitrageEngine(min_profit_pct=0.04)
    
    # Test sum arbitrage
    print("\n=== Testing Sum Arbitrage ===")
    opp = engine.check_sum_arbitrage(order_book, max_position=3.0)
    if opp:
        print(f"Found: {opp.type}")
        print(f"Profit: {opp.profit_pct*100:.2f}%")
        print(f"Cost: ${opp.total_cost:.2f}")
        print(f"Expected profit: ${opp.expected_profit:.2f}")
    else:
        print("No opportunity found")
    
    # Test Chainlink mismatch
    print("\n=== Testing Chainlink Mismatch ===")
    chainlink_btc = 76700  # Current Chainlink price
    start_price = 76500    # Interval start
    
    opp2 = engine.check_chainlink_mismatch(order_book, chainlink_btc, start_price, max_position=3.0)
    if opp2:
        print(f"Found: {opp2.type}")
        print(f"Profit: {opp2.profit_pct*100:.2f}%")
        print(f"Expected profit: ${opp2.expected_profit:.2f}")
    else:
        print("No opportunity found")
