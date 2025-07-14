import asyncio
import aiohttp
import logging
import json
import os
import time
from typing import Dict, Any

from utils import execute_buy, send_telegram_message, execute_sell, get_token_price

POSITIONS_FILE = "positions.json"
positions: Dict[str, Any] = {}  # {mint: {buy_price, tx, timestamp}}

# --- Logging setup ---
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

async def load_positions():
    """Load positions from disk."""
    global positions
    if os.path.exists(POSITIONS_FILE):
        try:
            with open(POSITIONS_FILE, "r") as f:
                positions = json.load(f)
            logging.info("✅ Positions loaded.")
        except Exception as e:
            logging.error(f"Failed to load positions: {e}")

async def save_positions():
    """Atomically save positions to disk."""
    try:
        tmp_file = POSITIONS_FILE + ".tmp"
        with open(tmp_file, "w") as f:
            json.dump(positions, f)
        os.replace(tmp_file, POSITIONS_FILE)
        logging.info("✅ Positions saved.")
    except Exception as e:
        logging.error(f"Failed to save positions: {e}")

async def scan_ryhad():
    """Fetch tokens from Ryhad API."""
    url = "https://ryhad.io/api/tokens"  # Replace with the real endpoint if needed
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url, timeout=10) as resp:
                if resp.status == 200:
                    return await resp.json()
                else:
                    logging.warning(f"Ryhad API returned status {resp.status}")
        except Exception as e:
            logging.error(f"Error fetching Ryhad tokens: {e}")
    return []

async def run_ryhad_scanner():
    """Scan Ryhad for new tokens and auto-buy if criteria met."""
    await load_positions()
    logging.info("📡 Ryhad scanner started.")
    seen = set(positions.keys())
    while True:
        tokens = await scan_ryhad()
        for token in tokens:
            mint = token.get("mint")
            try:
                liquidity = float(token.get("liquidity", 0))
                holders = float(token.get("holders", 0))
            except Exception as e:
                logging.error(f"Error parsing token data for {mint}: {e}")
                continue

            if not mint or mint in seen:
                continue
            if liquidity >= 10 and holders >= 10:
                logging.info(f"🚀 Ryhad auto-buying: {mint}")
                await send_telegram_message(f"🚀 Ryhad Auto-buy: {mint}\nLP: {liquidity}, Holders: {holders}")
                try:
                    success, tx = await execute_buy(mint, amount_usd=5)
                    if success:
                        price = await get_token_price(mint)
                        positions[mint] = {
                            "buy_price": price,
                            "tx": tx,
                            "timestamp": time.time()
                        }
                        await save_positions()
                        await send_telegram_message(f"✅ Ryhad Bought: {mint} at ${price:.4f}\nTx: {tx}")
                        seen.add(mint)
                    else:
                        await send_telegram_message(f"❌ Ryhad Buy failed: {mint}")
                except Exception as e:
                    logging.error(f"Error buying {mint}: {e}")
                    await send_telegram_message(f"❌ Ryhad Error buying {mint}: {e}")
            else:
                logging.info(f"Skipping {mint}: LP={liquidity}, Holders={holders}")
        await asyncio.sleep(10)

async def monitor_prices():
    """Monitor prices and auto-sell at 2x."""
    await load_positions()
    logging.info("📈 Ryhad price monitor started.")
    while True:
        to_remove = []
        for mint, data in positions.items():
            try:
                buy_price = float(data["buy_price"])
                current_price = await get_token_price(mint)
                if current_price >= buy_price * 2:
                    await send_telegram_message(f"💰 Selling {mint} at 2x: ${current_price:.4f}")
                    success, tx = await execute_sell(mint)
                    if success:
                        await send_telegram_message(f"✅ Sold {mint}\nTx: {tx}")
                        to_remove.append(mint)
                    else:
                        await send_telegram_message(f"❌ Sell failed for {mint}")
            except Exception as e:
                logging.error(f"Sell check failed for {mint}: {e}")
        for mint in to_remove:
            positions.pop(mint, None)
        if to_remove:
            await save_positions()
        await asyncio.sleep(60)

async def main():
    await asyncio.gather(
        run_ryhad_scanner(),
        monitor_prices()
    )

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        logging.critical(f"🔥 FATAL: Bot crashed at startup: {e}", exc_info=True)
