import asyncio
import json
import logging
import os
import signal
import sys
import time
from decimal import Decimal

# --- Dependency Check: aiohttp and solders ---
try:
    import aiohttp
except Exception as e:
    print(f"[startup][error] Failed to import aiohttp: {e}")
    sys.exit(1)
try:
    from solders.pubkey import Pubkey
except Exception as e:
    print(f"[startup][error] Failed to import solders.pubkey: {e}")
    sys.exit(1)

from dotenv import load_dotenv
from utils import (
    get_recent_tokens_from_helius,
    has_sufficient_liquidity,
    get_token_metadata,
    buy_token,
    get_token_price,
    sell_token,
    send_telegram_message
)

load_dotenv()

MIN_TOKEN_AGE_SECONDS = 0
MAX_TOKEN_AGE_SECONDS = 3600
MIN_LIQUIDITY_LAMPORTS = int(os.getenv("MIN_LIQUIDITY_LAMPORTS", 20 * 1_000_000_000))_*
