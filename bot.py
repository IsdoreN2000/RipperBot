import asyncio
import json
import logging
import os
import signal
import sys
import time
from decimal import Decimal

# Ensure all dependencies are present
try:
    import aiohttp
except Exception as e:
    print(f"[startup][error] Failed to import aiohttp: {e}")
    sys.exit(1)

try:
    from solders.pubkey import Pubkey  # Use solders for Solana public key handling
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
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

MIN_TOKEN_AGE_SECONDS = 60
MAX_TOKEN_AGE_SECONDS = 3600
MIN_LIQUIDITY_LAMPORTS = int(os.getenv("MIN_LIQUIDITY_LAMPORTS", 20 * 1_000_000_000))  # 20 SOL
BUY_AMOUNT_SOL = float(os.getenv("BUY_AMOUNT_SOL", 0.05))
PROFIT_TARGET = float(os.getenv("PROFIT_TARGET", 2.0))  # 2x
STOP_LOSS = float(os.getenv("STOP_LOSS", 0.5))          # 0.5x
POSITION_FILE = "positions.json"

PUMP_PROGRAM_ID = "G8ZbPXVwYhJcwhnXQpiN91n5PzFhHkHE7XQpHvVGh9v4"
BUNK_PROGRAM_ID = "BUNKU1mDhD6GNnpHJRZAZpEj3nGoqVZZe8RvAdTaLyoz"
TRACKED_PROGRAMS = [PUMP_PROGRAM_ID, BUNK_PROGRAM_ID]

shutdown_event = asyncio.Event()

def load_positions():
    if os.path.exists(POSITION_FILE):
        with open(POSITION_FILE, "r") as f:
            return json.load(f)
    return {}

def save_positions(positions):
    with open(POSITION_FILE, "w") as f:
        json.dump(positions, f, indent=2)

async def process_tokens():
    positions = load_positions()
    tokens = await get_recent_tokens_from_helius(TRACKED_PROGRAMS)
    logger.info(f"[main] Fetched {len(tokens)} tokens")

    now = time.time()
    for token in tokens:
        mint = token["mint"]
        timestamp = token.get("timestamp", now)
        age = now - timestamp

        logger.info(f"[check] {mint} age: {int(age)}s")

        if mint in positions:
            logger.info(f"[skip] {mint} already bought")
            continue
        if age < MIN_TOKEN_AGE_SECONDS:
            logger.info(f"[skip] {mint} too new ({int(age)}s)")
            continue
        if age > MAX_TOKEN_AGE_SECONDS:
            logger.info(f"[skip] {mint} too old ({int(age)}s)")
            continue

        if not await has_sufficient_liquidity(mint, MIN_LIQUIDITY_LAMPORTS):
            logger.info(f"[skip] {mint} insufficient liquidity")
            continue

        metadata = await get_token_metadata(mint)
        logger.info(f"[buy] {mint} | {metadata.get('symbol')}")

        await send_telegram_message(f"📥 Buying {metadata.get('symbol')} ({mint})")

        tx = await buy_token(mint, BUY_AMOUNT_SOL)
        if not tx.get("success"):
            logger.warning(f"[fail] buy failed: {tx.get('error')}")
            continue

        price = await get_token_price(mint)
        if price is None:
            logger.warning(f"[fail] price fetch failed after buy")
            continue

        positions[mint] = {
            "symbol": metadata.get("symbol"),
            "buy_price": price,
            "timestamp": time.time()
        }
        save_positions(positions)

async def monitor_positions():
    while not shutdown_event.is_set():
        positions = load_positions()
        for mint, data in positions.copy().items():
            buy_price = data["buy_price"]
            current_price = await get_token_price(mint)
            if current_price is None:
                continue
            change = current_price / buy_price

            logger.info(f"[track] {mint} | {data['symbol']} | x{change:.2f}")

            if change >= PROFIT_TARGET:
                await send_telegram_message(f"📈 Profit target reached for {data['symbol']} ({mint}), selling...")
                if await sell_token(mint):
                    del positions[mint]
                    save_positions(positions)
            elif change <= STOP_LOSS:
                await send_telegram_message(f"📉 Stop-loss triggered for {data['symbol']} ({mint}), selling...")
                if await sell_token(mint):
                    del positions[mint]
                    save_positions(positions)
        await asyncio.sleep(15)

async def main_loop():
    while not shutdown_event.is_set():
        try:
            await process_tokens()
        except Exception as e:
            logger.warning(f"[loop error] {e}")
        await asyncio.sleep(10)

async def main():
    await asyncio.gather(main_loop(), monitor_positions())

def shutdown_handler(sig, frame):
    logger.info(f"[shutdown] Signal received: {sig}")
    shutdown_event.set()

signal.signal(signal.SIGINT, shutdown_handler)
signal.signal(signal.SIGTERM, shutdown_handler)

if __name__ == "__main__":
    asyncio.run(main())
