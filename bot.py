import asyncio
import json
import logging
import os
import signal
import sys
import time
from decimal import Decimal
from dotenv import load_dotenv
from utils import (
    get_recent_tokens_from_helius,
    has_sufficient_liquidity,
    get_token_metadata,
    buy_token,
    get_token_price,
    sell_token,
    send_telegram_message,
    load_positions,
    save_positions,
    acquire_file_lock,
    release_file_lock
)

load_dotenv()

# --- Configurable Parameters ---
MIN_TOKEN_AGE_SECONDS = int(os.getenv("MIN_TOKEN_AGE_SECONDS", 60))
MAX_TOKEN_AGE_SECONDS = int(os.getenv("MAX_TOKEN_AGE_SECONDS", 3600))
MIN_LIQUIDITY_LAMPORTS = int(os.getenv("MIN_LIQUIDITY_LAMPORTS", 20 * 1_000_000_000))
BUY_AMOUNT_SOL = float(os.getenv("BUY_AMOUNT_SOL", 0.01))
PROFIT_TARGET_MULTIPLIER = float(os.getenv("PROFIT_TARGET_MULTIPLIER", 2.0))
STOP_LOSS_MULTIPLIER = float(os.getenv("STOP_LOSS_MULTIPLIER", 0.5))
TELEGRAM_ENABLED = os.getenv("TELEGRAM_ENABLED", "false").lower() == "true"
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", 5))
JITO_TIP = int(os.getenv("JITO_TIP", 5000))

# --- Program IDs for Pump.fun and Bunk.fun ---
PUMP_PROGRAM_IDS = [
    "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P",  # Pump.fun
    "BUNKU1mDhD6GNnpHJRZAZpEj3nGoqVZZe8RvAdTaLyoz"   # Bunk.fun
]

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s:%(message)s")
logger = logging.getLogger(__name__)

# Track positions
positions = {}
positions_file = "positions.json"
lock_file = "positions.lock"

# Graceful shutdown
running = True

def handle_shutdown(sig, frame):
    global running
    running = False
    logger.info("Shutting down...")

signal.signal(signal.SIGINT, handle_shutdown)
signal.signal(signal.SIGTERM, handle_shutdown)

async def monitor_tokens():
    global positions
    while running:
        try:
            token_mints = await get_recent_tokens_from_helius(PUMP_PROGRAM_IDS)
            logger.info(f"[main] Fetched {len(token_mints)} tokens")
            for token in token_mints:
                if not running:
                    break

                mint = token['mint']
                timestamp = token['timestamp']
                age = int(time.time()) - timestamp
                logger.info(f"[check] {mint}")

                if mint in positions:
                    continue
                if age < MIN_TOKEN_AGE_SECONDS:
                    logger.info(f"[skip] {mint} too new ({age}s)")
                    continue
                if age > MAX_TOKEN_AGE_SECONDS:
                    logger.info(f"[skip] {mint} too old ({age}s)")
                    continue

                if not await has_sufficient_liquidity(mint, MIN_LIQUIDITY_LAMPORTS):
                    logger.info(f"[skip] {mint} insufficient liquidity")
                    continue

                metadata = await get_token_metadata(mint)
                buy_response = await buy_token(mint, BUY_AMOUNT_SOL, tip=JITO_TIP)
                if buy_response['success']:
                    buy_price = await get_token_price(mint)
                    if buy_price is None:
                        logger.warning(f"[warn] {mint} bought but failed to fetch price")
                        continue

                    logger.info(f"[buy] {mint} at price {buy_price}")
                    if TELEGRAM_ENABLED:
                        await send_telegram_message(f"Bought {metadata['name']} ({mint}) at price {buy_price}")

                    positions[mint] = {
                        "buy_price": buy_price,
                        "timestamp": int(time.time()),
                        "metadata": metadata
                    }
                    await save_positions(positions_file, positions, lock_file)
                else:
                    logger.info(f"[skip] {mint} buy failed: {buy_response['error']}")

            # Check sell conditions
            for mint, data in list(positions.items()):
                current_price = await get_token_price(mint)
                if current_price is None:
                    continue
                buy_price = data['buy_price']
                if current_price >= buy_price * PROFIT_TARGET_MULTIPLIER:
                    logger.info(f"[sell] {mint} hit profit target: {current_price}")
                    await sell_token(mint)
                    if TELEGRAM_ENABLED:
                        await send_telegram_message(f"Sold {data['metadata']['name']} ({mint}) for profit at {current_price}")
                    positions.pop(mint)
                    await save_positions(positions_file, positions, lock_file)
                elif current_price <= buy_price * STOP_LOSS_MULTIPLIER:
                    logger.info(f"[sell] {mint} hit stop loss: {current_price}")
                    await sell_token(mint)
                    if TELEGRAM_ENABLED:
                        await send_telegram_message(f"Sold {data['metadata']['name']} ({mint}) for loss at {current_price}")
                    positions.pop(mint)
                    await save_positions(positions_file, positions, lock_file)

            await asyncio.sleep(POLL_INTERVAL)
        except Exception as e:
            logger.exception(f"[error] {str(e)}")
            await asyncio.sleep(5)

async def main():
    logger.info("Starting bot...")
    await acquire_file_lock(lock_file)
    global positions
    positions = await load_positions(positions_file)
    try:
        await monitor_tokens()
    finally:
        await save_positions(positions_file, positions, lock_file)
        await release_file_lock(lock_file)

if __name__ == "__main__":
    asyncio.run(main())
