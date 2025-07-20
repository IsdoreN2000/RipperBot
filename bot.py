import asyncio
import logging
import signal
import sys
import time
import json
import aiofiles
import aiofiles.os
import os
from utils import (
    get_recent_tokens_from_helius,
    check_liquidity,
    should_buy_token,
    execute_buy,
    monitor_and_sell,
    load_positions,
    save_positions,
    telegram_alert
)

logging.basicConfig(level=logging.INFO)

PROGRAM_IDS = [
    "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P",  # Pump.fun
    "BUNKU1mDhD6GNnpHJRZAZpEj3nGoqVZZe8RvAdTaLyoz"   # Bunk.fun (correct ID)
]

FETCH_INTERVAL = 5  # seconds
POSITIONS_FILE = "positions.json"
positions = load_positions()
seen_tokens = set(token["mint"] for token in positions)

running = True

def handle_sigterm(*args):
    global running
    running = False
    logging.info("[shutdown] Gracefully shutting down...")
    save_positions(positions)
    sys.exit(0)

signal.signal(signal.SIGTERM, handle_sigterm)
signal.signal(signal.SIGINT, handle_sigterm)

async def safe_get_tokens(program_id):
    retries = 3
    for attempt in range(retries):
        try:
            tokens = await get_recent_tokens_from_helius(program_id)
            return tokens
        except Exception as e:
            logging.warning(f"[retry] Fetch failed for {program_id}, attempt {attempt+1}/{retries}: {e}")
            await asyncio.sleep(1)
    return []

async def main():
    logging.info("[main] Bot started")

    while running:
        all_tokens = []

        for program_id in PROGRAM_IDS:
            tokens = await safe_get_tokens(program_id)
            logging.info(f"[main] Fetched {len(tokens)} tokens from {program_id}")
            all_tokens.extend(tokens)

        for token in all_tokens:
            mint = token["mint"]
            if mint in seen_tokens:
                continue

            logging.info(f"[check] {mint}")

            if not should_buy_token(token):
                logging.info(f"[skip] {mint} did not pass filters")
                continue

            if not await check_liquidity(mint):
                logging.info(f"[skip] {mint} insufficient liquidity")
                continue

            bought = await execute_buy(mint)
            if bought:
                seen_tokens.add(mint)
                timestamp = int(time.time())
                positions.append({"mint": mint, "bought_at": timestamp})
                save_positions(positions)
                telegram_alert(f"✅ Bought token: {mint}")
                asyncio.create_task(monitor_and_sell(mint, positions, seen_tokens))

        await asyncio.sleep(FETCH_INTERVAL)

if __name__ == "__main__":
    asyncio.run(main())
