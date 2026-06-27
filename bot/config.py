"""
BSC Sniper Bot — Configuration
"""
from web3 import Web3

# ── RPC Endpoint ──────────────────────────────
RPC_URL = "https://bsc-dataseed1.binance.org"

# ── Wallet ────────────────────────────────────
# Private key (set via env var TRADER_PRIVATE_KEY for security)
PRIVATE_KEY = "***"  # Use TRADER_PRIVATE_KEY env var

# Your wallet address
WALLET_ADDRESS = "0x6A3404e7fdeE519AaaB364E1C27Db07aa99Ec922"

# ── Trading Parameters ────────────────────────
TRADE_SIZE_BNB = 0.001          # BNB per snipe
MAX_SNIPES = 5                  # Max concurrent positions
PROFIT_TARGET = 2.0             # 2x = sell at 100% gain
STOP_LOSS = 0.3                 # 0.3x = sell at 70% loss
MAX_HOLD_TIME = 3600            # Max hold time in seconds (1 hour)

# ── Monitoring ────────────────────────────────
POLL_INTERVAL = 15              # Seconds between pair checks
DRY_RUN = True                  # Safe mode
