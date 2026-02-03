"""
Execution Manager for Polymarket Arbitrage Bot

Handles:
1. Parallel order submission (for sum-to-one arbitrage)
2. Fill verification and monitoring
3. Position tracking
4. Error handling and retries

Uses py_clob_client for order submission on Polymarket CLOB.
"""
import asyncio
import logging
import time
from typing import Dict, Optional, List, Tuple
from dataclasses import dataclass
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import OrderArgs, OrderType, BalanceAllowanceParams, AssetType
from py_clob_client.constants import POLYGON

logger = logging.getLogger(__name__)


@dataclass
class OrderResult:
    """Result of an order submission"""
    success: bool
    order_id: Optional[str] = None
    filled_size: float = 0.0
    error: Optional[str] = None
    timestamp: float = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = time.time()


@dataclass
class Position:
    """Tracks an open position"""
    market_id: str
    token_id: str
    side: str  # "up" or "down"
    size: float
    entry_price: float
    entry_time: float
    cost: float


class ExecutionManager:
    """Manage order execution and position tracking"""
    
    def __init__(self, client: ClobClient):
        self.client = client
        self.positions: List[Position] = []
        self.pending_orders: Dict[str, OrderArgs] = {}
        
        logger.info("Execution Manager initialized")
    
    async def execute_sum_arbitrage(
        self, 
        market_id: str,
        up_token_id: str,
        down_token_id: str,
        up_price: float,
        down_price: float,
        size: float
    ) -> Tuple[bool, str]:
        """
        Execute sum-to-one arbitrage (buy both Up and Down)
        
        Orders are submitted in parallel to minimize execution risk.
        
        Returns:
            (success, message)
        """
        logger.info(f"Executing sum arbitrage: {size:.2f} shares @ Up=${up_price:.3f}, Down=${down_price:.3f}")
        
        try:
            # Create order arguments
            up_order = OrderArgs(
                token_id=up_token_id,
                price=up_price,
                size=size,
                side="BUY",
                order_type=OrderType.GTC  # Good-til-canceled
            )
            
            down_order = OrderArgs(
                token_id=down_token_id,
                price=down_price,
                size=size,
                side="BUY",
                order_type=OrderType.GTC
            )
            
            # Submit orders in parallel
            results = await asyncio.gather(
                self._submit_order(up_order, "Up"),
                self._submit_order(down_order, "Down"),
                return_exceptions=True
            )
            
            up_result, down_result = results
            
            # Check if both succeeded
            if isinstance(up_result, Exception) or isinstance(down_result, Exception):
                error_msg = f"Order submission failed: Up={up_result}, Down={down_result}"
                logger.error(error_msg)
                
                # Cancel any successful orders
                if not isinstance(up_result, Exception) and up_result.order_id:
                    await self._cancel_order(up_result.order_id)
                if not isinstance(down_result, Exception) and down_result.order_id:
                    await self._cancel_order(down_result.order_id)
                
                return False, error_msg
            
            if not up_result.success or not down_result.success:
                error_msg = f"Order execution failed: Up={up_result.error}, Down={down_result.error}"
                logger.error(error_msg)
                
                # Cancel successful order if one failed
                if up_result.success and up_result.order_id:
                    await self._cancel_order(up_result.order_id)
                if down_result.success and down_result.order_id:
                    await self._cancel_order(down_result.order_id)
                
                return False, error_msg
            
            # Both orders placed successfully
            logger.info(f"Both orders placed: Up={up_result.order_id}, Down={down_result.order_id}")
            
            # Wait for fills
            up_filled = await self._wait_for_fill(up_result.order_id, up_token_id, size)
            down_filled = await self._wait_for_fill(down_result.order_id, down_token_id, size)
            
            if up_filled and down_filled:
                # Track positions
                self.positions.append(Position(
                    market_id=market_id,
                    token_id=up_token_id,
                    side="up",
                    size=size,
                    entry_price=up_price,
                    entry_time=time.time(),
                    cost=size * up_price
                ))
                
                self.positions.append(Position(
                    market_id=market_id,
                    token_id=down_token_id,
                    side="down",
                    size=size,
                    entry_price=down_price,
                    entry_time=time.time(),
                    cost=size * down_price
                ))
                
                success_msg = f"Sum arbitrage executed: {size:.2f} shares each side"
                logger.info(success_msg)
                return True, success_msg
            else:
                # Partial fill - need to handle
                error_msg = "Partial fill - manual intervention required"
                logger.warning(error_msg)
                return False, error_msg
                
        except Exception as e:
            error_msg = f"Execution error: {e}"
            logger.error(error_msg)
            return False, error_msg
    
    async def execute_single_side(
        self,
        market_id: str,
        token_id: str,
        side: str,  # "up" or "down"
        price: float,
        size: float
    ) -> Tuple[bool, str]:
        """
        Execute single-side order (for Chainlink mismatch)
        
        Returns:
            (success, message)
        """
        logger.info(f"Executing {side.upper()} order: {size:.2f} shares @ ${price:.3f}")
        
        try:
            order = OrderArgs(
                token_id=token_id,
                price=price,
                size=size,
                side="BUY",
                order_type=OrderType.GTC
            )
            
            result = await self._submit_order(order, side.upper())
            
            if not result.success:
                return False, f"Order failed: {result.error}"
            
            # Wait for fill
            filled = await self._wait_for_fill(result.order_id, token_id, size)
            
            if filled:
                # Track position
                self.positions.append(Position(
                    market_id=market_id,
                    token_id=token_id,
                    side=side,
                    size=size,
                    entry_price=price,
                    entry_time=time.time(),
                    cost=size * price
                ))
                
                success_msg = f"{side.upper()} order filled: {size:.2f} shares @ ${price:.3f}"
                logger.info(success_msg)
                return True, success_msg
            else:
                return False, "Order did not fill in time"
                
        except Exception as e:
            error_msg = f"Execution error: {e}"
            logger.error(error_msg)
            return False, error_msg
    
    async def _submit_order(self, order: OrderArgs, label: str = "") -> OrderResult:
        """
        Submit a single order to Polymarket
        
        Args:
            order: Order arguments
            label: Human-readable label for logging
        
        Returns:
            OrderResult
        """
        try:
            logger.debug(f"Submitting {label} order: {order.size} @ ${order.price}")
            
            # Submit order using py_clob_client
            response = self.client.create_order(order)
            
            if response.get("success"):
                order_id = response.get("orderID")
                logger.info(f"{label} order placed: {order_id}")
                
                return OrderResult(
                    success=True,
                    order_id=order_id
                )
            else:
                error = response.get("error", "Unknown error")
                logger.error(f"{label} order failed: {error}")
                return OrderResult(
                    success=False,
                    error=error
                )
                
        except Exception as e:
            logger.error(f"{label} order exception: {e}")
            return OrderResult(
                success=False,
                error=str(e)
            )
    
    async def _wait_for_fill(
        self, 
        order_id: str, 
        token_id: str, 
        expected_size: float,
        timeout: int = 30
    ) -> bool:
        """
        Wait for order to fill
        
        Uses ultra-fast polling (0.1s intervals) to detect fills quickly.
        
        Returns:
            True if filled, False if timeout
        """
        logger.info(f"Monitoring fill for order {order_id}")
        
        checks = 0
        max_checks = timeout * 10  # 0.1s intervals
        
        while checks < max_checks:
            await asyncio.sleep(0.1)
            checks += 1
            
            try:
                # Check order status
                order_status = self.client.get_order(order_id)
                status = order_status.get("status", "").lower()
                size_filled = float(order_status.get("size_filled", "0"))
                
                if status == "closed" or size_filled >= expected_size:
                    logger.info(f"Order {order_id} filled: {size_filled:.2f} shares")
                    return True
                elif status == "canceled":
                    logger.warning(f"Order {order_id} was canceled")
                    return False
                
                # Progress indicator every 5 seconds
                if checks % 50 == 0:
                    logger.debug(f"  Still waiting for fill... ({checks/10:.1f}s elapsed)")
                    
            except Exception as e:
                if checks % 50 == 0:
                    logger.debug(f"  Fill check error: {e}")
        
        logger.warning(f"Order {order_id} did not fill within {timeout}s")
        return False
    
    async def _cancel_order(self, order_id: str):
        """Cancel an order"""
        try:
            self.client.cancel_order(order_id)
            logger.info(f"Canceled order {order_id}")
        except Exception as e:
            logger.error(f"Failed to cancel order {order_id}: {e}")
    
    def get_positions(self, market_id: Optional[str] = None) -> List[Position]:
        """Get all positions, optionally filtered by market"""
        if market_id:
            return [p for p in self.positions if p.market_id == market_id]
        return self.positions
    
    def calculate_pnl(self, settlement_prices: Dict[str, float]) -> float:
        """
        Calculate total P&L based on settlement prices
        
        Args:
            settlement_prices: {token_id: settlement_value}
            
        Returns:
            Total P&L
        """
        total_cost = sum(p.cost for p in self.positions)
        total_value = sum(
            p.size * settlement_prices.get(p.token_id, 0)
            for p in self.positions
        )
        
        pnl = total_value - total_cost
        return pnl


# Test
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    print("Execution Manager - Unit Tests")
    print("(Requires active Polymarket connection to test fully)")
    
    # Demo: Calculate PnL for sum arbitrage
    print("\n=== Sum Arbitrage P&L Simulation ===")
    
    # Simulate positions
    positions = [
        Position(
            market_id="btc-updown-15m-123",
            token_id="up_token",
            side="up",
            size=3.0,
            entry_price=0.45,
            entry_time=time.time(),
            cost=3.0 * 0.45
        ),
        Position(
            market_id="btc-updown-15m-123",
            token_id="down_token",
            side="down",
            size=3.0,
            entry_price=0.48,
            entry_time=time.time(),
            cost=3.0 * 0.48
        )
    ]
    
    total_cost = sum(p.cost for p in positions)
    print(f"Total Cost: ${total_cost:.2f}")
    
    # Simulate settlement (Up wins)
    settlement = {"up_token": 1.0, "down_token": 0.0}
    total_value = sum(p.size * settlement[p.token_id] for p in positions)
    print(f"Settlement Value: ${total_value:.2f}")
    
    pnl = total_value - total_cost
    print(f"Profit: ${pnl:.2f} ({pnl/total_cost*100:.1f}%)")
