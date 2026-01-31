import polars as pl
import numpy as np
from dataclasses import dataclass, field
from typing import List, Optional, Deque, Dict
from collections import deque

@dataclass
class LimitOrder:
    id: str
    side: str # 'BUY' or 'SELL'
    price: float
    size: float
    entry_time: int
    status: str = "OPEN" # OPEN, FILLED, CANCELED, REPLACED
    time_on_book: int = 0  # Nanoseconds spent at the touch

class TickTester:
    def __init__(self, file_path: str):
        self.file_path = file_path
        self.df = None
        self.orders: List[LimitOrder] = []
        self.position = 0.0
        self.cash = 0.0
        self.trade_log = []
        
        # Performance Metrics
        self.volume_traded = 0.0
        
        # State
        self.active_buy: Optional[LimitOrder] = None
        self.active_sell: Optional[LimitOrder] = None
        
        # Config
        self.latency_ns = 50 * 1_000_000 # 50ms latency
        self.queue_wait_ns = 1_000 * 1_000_000 # 1 second wait time for "Front of Queue" probability
        self.starting_cash = 100_000.0
        self.max_position = 50_000 # Max units
        self.lot_size = 1000

    def load_data(self):
        print(f"Loading {self.file_path}...")
        self.df = pl.read_parquet(self.file_path).sort("timestamp")
        print(f"Loaded {len(self.df)} ticks.")

    def run_backtest(self):
        if self.df is None: self.load_data()
        
        timestamps = self.df["timestamp"].cast(pl.Int64).to_numpy()
        bids = self.df["bid"].to_numpy()
        asks = self.df["ask"].to_numpy()
        
        print(f"Starting Simulation on {len(timestamps)} ticks (Queue Wait: 1s)...")
        
        last_ts = 0
        
        for i in range(len(timestamps)):
            ts = timestamps[i]
            bid = bids[i]
            ask = asks[i]
            
            # Calculate time delta for queue accumulation
            dt = ts - last_ts if last_ts > 0 else 0
            last_ts = ts
            
            # 1. Latency & Fill Check (Queue Sim)
            self._check_fills_queue(ts, bid, ask, dt)
            
            # 2. Strategy Logic (Market Maker)
            self._strategy_mm_flip(ts, bid, ask)
            
            # Logging
            if i % 500_000 == 0:
                equity = self.cash + (self.position * ((bid+ask)/2))
                print(f"Tick {i}: Eq={equity:.2f} Pos={self.position} (B:{bid} A:{ask})")

        # Final Settlement
        final_price = (bids[-1] + asks[-1]) / 2
        equity = self.cash + (self.position * final_price)
        print(f"\n--- Simulation Complete ---")
        print(f"Final Equity: {equity:.2f}")
        print(f"Total Traded: {self.volume_traded}")
        print(f"Total Trades: {len(self.trade_log)}")
        if len(self.trade_log) > 0:
            print(f"First Trade: {self.trade_log[0]}")
            print(f"Last Trade: {self.trade_log[-1]}")

    def _strategy_mm_flip(self, ts, bid, ask):
        """
        Skewed Market Maker with Micro-Trend Protection:
        - Calculates Short-Term Trend (RoC).
        - If Trend is adverse, PULL QUOTES (Don't catch knives).
        - If Trend is neutral, Provide Liquidity with Skew.
        """
        entry_ts = ts + self.latency_ns
        mid = (bid + ask) / 2
        
        # 0. Update Price History for Trend Calc
        # We need state persistence. Add this to __init__ in real implementation, 
        # but for this script we can cheat or add it now.
        if not hasattr(self, "price_history"):
            self.price_history = deque(maxlen=100)
            
        self.price_history.append(mid)
        
        # 1. Calculate Trend (Velocity)
        # Simple Delta: Current - Avg(Last 10) or Current - Last 50?
        # Let's use Current - Price[t-50]
        
        trend_signal = 0.0 # Neutral
        if len(self.price_history) == 100:
            past_mid = self.price_history[0]
            # Velocity = Change per 100 ticks
            velocity = mid - past_mid
            
            # Threshold: If move > 1 spread (approx 1 pip = 1.0?), wait.
            # NSX spread is ~1.0 to 1.5 ticks? (0.25 index points?)
            # Ticks are raw price. Spread ~ 0.5 to 1.0 points usually.
            spread = ask - bid
            threshold = spread * 1.5 # Significant move
            
            if velocity > threshold: trend_signal = 1.0 # Up Trend
            elif velocity < -threshold: trend_signal = -1.0 # Down Trend
        
        # 2. Inventory Skew (Avellaneda)
        skew_intensity = 5.0
        skew_ticks = (self.position / 10000.0) * skew_intensity
        reservation_price = mid - skew_ticks 
        
        half_spread = (ask - bid) / 2
        target_buy_price = round(reservation_price - half_spread, 3)
        target_sell_price = round(reservation_price + half_spread, 3)
        
        # 3. Execution Logic with Trend Filter
        
        # BUY SIDE
        # If Trend is DOWN (-1.0), DO NOT BID. Pull existing Bids.
        # Unless we are Short and need to cover? (Maybe aggressive buy?)
        # For now, "Hide" logic: If Trend Down, Pull Bid.
        
        allow_buy = True
        if trend_signal == -1.0:
            if self.position > 0: allow_buy = False # Don't add to long in downtrend
            # If short, maybe we still buy to cover?
        
        if allow_buy and self.position < self.max_position:
            if self.active_buy is None:
                self.active_buy = self._place_order("BUY", target_buy_price, self.lot_size, entry_ts)
            elif abs(self.active_buy.price - target_buy_price) > 0.005: 
                self.active_buy.status = "CANCELED"
                self.active_buy = self._place_order("BUY", target_buy_price, self.lot_size, entry_ts)
        else:
            if self.active_buy:
                self.active_buy.status = "CANCELED"
                self.active_buy = None

        # SELL SIDE
        # If Trend is UP (1.0), DO NOT OFFER. Pull existing Asks.
        
        allow_sell = True
        if trend_signal == 1.0:
            if self.position < 0: allow_sell = False # Don't add to short in uptrend
        
        if allow_sell and self.position > -self.max_position:
             if self.active_sell is None:
                self.active_sell = self._place_order("SELL", target_sell_price, self.lot_size, entry_ts)
             elif abs(self.active_sell.price - target_sell_price) > 0.005:
                self.active_sell.status = "CANCELED"
                self.active_sell = self._place_order("SELL", target_sell_price, self.lot_size, entry_ts)
        else:
            if self.active_sell:
                self.active_sell.status = "CANCELED"
                self.active_sell = None

    def _check_fills_queue(self, current_ts, bid, ask, dt):
        """
        Queue Logic:
        - Trade Through: Instant Fill.
        - Trade At (Touch): Accumulate time. If time > queue_wait, Fill.
        """
        # Checks Active Buy
        if self.active_buy and self.active_buy.status == "OPEN":
            if current_ts >= self.active_buy.entry_time:
                # 1. Trade Through (Ask < Bid_Order)
                if ask < self.active_buy.price: 
                    self._fill_order(self.active_buy, self.active_buy.price, current_ts)
                    self.active_buy = None 
                
                # 2. Trade At (Bid == Bid_Order) -> We are on the book.
                # If Market Bid == Order Price, we accumulate time.
                elif bid == self.active_buy.price:
                    self.active_buy.time_on_book += dt
                    if self.active_buy.time_on_book >= self.queue_wait_ns:
                        # Filled at Limit Price
                        self._fill_order(self.active_buy, self.active_buy.price, current_ts)
                        self.active_buy = None
                
                # 3. Price Moved Away (Bid > Order) -> We are behind.
                # Reset Queue? Or Keep? 
                # If Bid improves (Bid > Order), we are no longer at the touch.
                else: 
                     # If we are NOT at the touch, we don't accumulate "front of queue" credit? 
                     # Actually, if we are behind, we definitely don't get filled.
                     # We only reset if we cancel/replace (which strategy does).
                     pass

        # Checks Active Sell
        if self.active_sell and self.active_sell.status == "OPEN":
            if current_ts >= self.active_sell.entry_time:
                if bid > self.active_sell.price: # Trade Through
                    self._fill_order(self.active_sell, self.active_sell.price, current_ts)
                    self.active_sell = None 
                
                elif ask == self.active_sell.price: # At Touch
                    self.active_sell.time_on_book += dt
                    if self.active_sell.time_on_book >= self.queue_wait_ns:
                        self._fill_order(self.active_sell, self.active_sell.price, current_ts)
                        self.active_sell = None

    def _place_order(self, side, price, size, entry_time) -> LimitOrder:
        order = LimitOrder(id=f"{len(self.orders)}", side=side, price=price, size=size, entry_time=entry_time)
        return order

    def _fill_order(self, order, price, time):
        order.status = "FILLED"
        if order.side == "BUY":
            self.position += order.size
            self.cash -= price * order.size
        else:
            self.position -= order.size
            self.cash += price * order.size
            
        self.volume_traded += order.size
        self.trade_log.append({"time": time, "side": order.side, "price": price, "qty": order.size})

if __name__ == "__main__":
    # Test on the file we found
    path = "/Users/danielfisher/Desktop/tick/NSXUSD/NSXUSD_202401_ticks.parquet"
    bot = TickTester(path)
    bot.run_backtest()
