import asyncio
import json
import logging
import os
import signal
import sys
import time
from decimal import Decimal

# --- Dependency Check: solana and aiohttp ---
try:
    import aiohttp
except Exception as e:
    print(f"[startup][error] Failed to import aiohttp: {e}")
    sys.exit(1)
try:
    from solana.publickey import PublicKey
except Exception as e:
    print(f"[startup][error] Failed to import solana.publickey: {e}")
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
MIN_LIQUIDITY_LAMPORTS = int(os.getenv("MIN_LIQUIDITY_LAMPORTS", 20 * 1_000_000_000))
BUY_AMOUNT_SOL = float(os.getenv("BUY_AMOUNT_SOL", 0.01))
PROFIT_TARGET_MULTIPLIER = float(os.getenv("PROFIT_TARGET_MULTIPLIER", 2.0))
STOP_LOSS_MULTIPLIER = float(os.getenv("STOP_LOSS_MULTIPLIER", 0.5))
TELEGRAM_ENABLED = os.getenv("TELEGRAM_ENABLED", "false").lower() == "true"
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", 5))
JITO_TIP = int(os.getenv("JITO_TIP", 5000))

PUMP_PROGRAM_IDS = [
    "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P",  # Pump.fun
    "BUNKU1mDhD6GNnpHJRZAZpEj3nGoqVZZe8RvAdTaLyoz"   # Bunk.fun
]

positions = {}
POSITIONS_FILE = "positions.json"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

running = True

def handle_shutdown(sig, frame):
    global running
    running = False
    logger.info("Shutting down...")

signal.signal(signal.SIGINT, handle_shutdown)
signal.signal(signal.SIGTERM, handle_shutdown)

def load_positions():
    try:
        if os.path.exists(POSITIONS_FILE):
            with open(POSITIONS_FILE, "r") as f:
                return json.load(f)
    except Exception as e:
        logger.warning(f"Could not load positions: {e}")
    return {}

def save_positions():
    try:
        with open(POSITIONS_FILE, "w") as f:
            json.dump(positions, f)
    except Exception as e:
        logger.warning(f"Could not save positions: {e}")

async def monitor():
    global positions
    while running:
        try:
            tokens = await get_recent_tokens_from_helius(PUMP_PROGRAM_IDS)
            logger.info(f"Fetched {len(tokens)} tokens")

            for token in tokens:
                if not running:
                    break
                mint = token['mint']
                timestamp = token['timestamp']
                age = int(time.time()) - timestamp

                if mint in positions:
                    continue
                if age < MIN_TOKEN_AGE_SECONDS or age > MAX_TOKEN_AGE_SECONDS:
                    continue

                logger.info(f"[check] {mint}")

                if not await has_sufficient_liquidity(mint, MIN_LIQUIDITY_LAMPORTS):
                    logger.info(f"[skip] {mint} insufficient liquidity")
                    continue

                metadata = await get_token_metadata(mint)
                buy_result = await buy_token(mint, BUY_AMOUNT_SOL, tip=JITO_TIP)

                if buy_result['success']:
                    price = await get_token_price(mint)
                    if price is None:
                        logger.warning(f"[warn] {mint} bought but no price")
                        continue

                    logger.info(f"[buy] {mint} at {price}")
                    if TELEGRAM_ENABLED:
                        await send_telegram_message(f"Bought {metadata['name']} ({mint}) at price {price}")

                    positions[mint] = {
                        "buy_price": price,
                        "timestamp": int(time.time()),
                        "metadata": metadata
                    }
                    save_positions()
                else:
                    logger.info(f"[fail] {mint} buy failed: {buy_result.get('error', 'Unknown error')}")

            for mint, data in list(positions.items()):
                price = await get_token_price(mint)
                if not price:
                    continue
                buy_price = data['buy_price']
                if price >= buy_price * PROFIT_TARGET_MULTIPLIER:
                    await sell_token(mint)
                    logger.info(f"[sell] {mint} for profit at {price}")
                    if TELEGRAM_ENABLED:
                        await send_telegram_message(f"Sold {data['metadata']['name']} for profit at {price}")
                    positions.pop(mint)
                    save_positions()
                elif price <= buy_price * STOP_LOSS_MULTIPLIER:
                    await sell_token(mint)
                    logger.info(f"[sell] {mint} stop loss at {price}")
                    if TELEGRAM_ENABLED:
                        await send_telegram_message(f"Sold {data['metadata']['name']} for loss at {price}")
                    positions.pop(mint)
                    save_positions()

            await asyncio.sleep(POLL_INTERVAL)

        except Exception as e:
            logger.exception(f"Error: {e}")
            await asyncio.sleep(5)

async def main():
    logger.info("Starting bot...")
    global positions
    positions = load_positions()
    await monitor()

if __name__ == "__main__":
    logger.info("Launching Solana trading bot...")
    asyncio.run(main())
