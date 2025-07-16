import os
import json
import base64
import aiohttp
import logging
import signal
import sys
from datetime import datetime, timezone
from solders.keypair import Keypair
from solders.transaction import VersionedTransaction
from solana.rpc.async_api import AsyncClient
from solana.rpc.types import TxOpts
import asyncio
import traceback

logging.basicConfig(level=logging.INFO)
logging.info("=== Bot started successfully ===")

MAX_TOKEN_AGE_SECONDS = 30 * 60  # Buy tokens that are between 0 and 30 minutes old
MIN_LIQUIDITY_LAMPORTS = 20 * 1_000_000_000  # 20 SOL

# --- ENVIRONMENT VARIABLES & VALIDATION ---
REQUIRED_ENVS = [
    "PRIVATE_KEY", "HELIUS_API_KEY", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"
]
for var in REQUIRED_ENVS:
    if not os.getenv(var):
        logging.error(f"Missing required environment variable: {var}")
        sys.exit(1)

try:
    PRIVATE_KEY = json.loads(os.getenv("PRIVATE_KEY"))
    keypair = Keypair.from_bytes(bytes(PRIVATE_KEY))
except Exception as e:
    logging.error(f"Invalid PRIVATE_KEY format: {e}")
    sys.exit(1)

HELIUS_API_KEY = os.getenv("HELIUS_API_KEY")
RPC_URL = os.getenv("RPC_URL", f"https://mainnet.helius-rpc.com/?api-key={HELIUS_API_KEY}")
BUY_AMOUNT_SOL = float(os.getenv("BUY_AMOUNT_SOL", 0.01))
SLIPPAGE = float(os.getenv("SLIPPAGE", 3))
PROFIT_TARGET = float(os.getenv("PROFIT_TARGET", 1.5))
STOP_LOSS = float(os.getenv("STOP_LOSS", 0.7))
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
HELIUS_URL = f"https://mainnet.helius-rpc.com/?api-key={HELIUS_API_KEY}"
PUMP_PROGRAM_ID = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
JUPITER_QUOTE_URL = "https://quote-api.jup.ag/v6/quote"
JUPITER_SWAP_URL = "https://quote-api.jup.ag/v6/swap"
WRAPPED_SOL = "So11111111111111111111111111111111111111112"
POSITIONS_FILE = "positions.json"

# (The rest of the logic stays the same, only change needed is to use MAX_TOKEN_AGE_SECONDS instead of MIN)
# In your main_loop or wherever you check token age, ensure:
#
# if creation_time:
#     age = datetime.now(timezone.utc).timestamp() - creation_time
#     if age > MAX_TOKEN_AGE_SECONDS:
#         logging.info(f"[skip] {mint} too old ({int(age)}s)")
#         continue
#
