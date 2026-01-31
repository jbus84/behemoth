import json
import os
from datetime import datetime
import threading

class SignalLogger:
    """
    Handles thread-safe logging of trading signals to a JSON ledger.
    Path: logs/live_signals.json
    """
    def __init__(self, log_dir="logs", filename="live_signals.json"):
        self.log_dir = log_dir
        self.filepath = os.path.join(log_dir, filename)
        self.lock = threading.Lock()
        
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)
            
        # Initialize file if not exists
        if not os.path.exists(self.filepath):
            with open(self.filepath, 'w') as f:
                json.dump([], f)

    def log_signal(self, strategy: str, action: str, symbol: str, price: float, timestamp: str, metadata: dict = None):
        """
        Appends a signal event to the log file.
        """
        event = {
            "timestamp_utc": timestamp,
            "local_time": datetime.utcnow().isoformat(),
            "strategy": strategy,
            "action": action, # BUY / SELL / CLOSE
            "symbol": symbol,
            "price": price,
            "metadata": metadata or {}
        }
        
        with self.lock:
            try:
                # Read existing
                with open(self.filepath, 'r') as f:
                    try:
                        data = json.load(f)
                    except json.JSONDecodeError:
                        data = []
                
                # Append
                data.append(event)
                
                # Write back
                with open(self.filepath, 'w') as f:
                    json.dump(data, f, indent=4)
                    
                print(f"[{timestamp}] SIGNAL LOGGED: {strategy} {action} @ {price}")
                
            except Exception as e:
                print(f"ERROR LOGGING SIGNAL: {e}")

if __name__ == "__main__":
    # Test
    logger = SignalLogger()
    logger.log_signal("TEST_STRATEGY", "BUY", "NSXUSD", 15000.50, datetime.utcnow().isoformat(), {"vol": 1.2})
