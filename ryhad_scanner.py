import asyncio
import aiohttp
import logging
import json
import os
import time
from typing import Dict, Set, Any

from utils import execute_buy, execute_sell, get_token_price, send_telegram_message

# --- Copy Trading Setup ---
WATCHED_WALLETS = [
    "8CKfrsQkdrkwyZpXVPXTqBo37Ep5dWq2UKR7o2L3TfVu",
    "Dj8v6HkSSQ8j2RWkLq8Dw4xZ5XPq6pEGpEV9nPUqtrzU",
    "GZ6PEx2R3GqmvUw8EWEAxEA5etC7mDAv4aHaKq2RY1nD"
]
wallet_token_cache: Dict[str, Set[str]] = {}

# --- Auto Trading Setup ---
AUTO_TRADE_API = "https://api-v3.raydium.io/pools"
auto_trade_seen: Set[str] = set()

# --- Shared Position Tracking ---
POSITIONS_FILE = "positions.json"
positions: Dict[str, Dict[str, Any]] = {}

CACHE_FILE = "token_cache.json"
AUTO_TRADE_SEEN_FILE = "auto_trade_seen.json"

# --- Persistence ---
def save_cache():
    try:
        with open(CACHE_FILE, "w") as f:
            json.dump({k: list(v) for k, v in wallet_token_cache.items()}, f)
        logging.info("✅ Token cache saved.")
    except Exception as e:
        logging.error(f"Failed to save token cache: {e}")

def load_cache():
    global wallet_token_cache
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r") as f:
                wallet_token_cache = {k: set(v) for k, v in json.load(f).items()}
            logging.info("✅ Token cache loaded.")
        except Exception as e:
            wallet_token_cache = {}
            logging.error(f"Failed to load token cache: {e}")
    else:
        wallet_token_cache = {}

def save_positions():
    try:
        tmp_file = POSITIONS_FILE + ".tmp"
        with open(tmp_file, "w") as f:
            json.dump(positions, f)
        os.replace(tmp_file, POSITIONS_FILE)
        logging.info("✅ Positions saved.")
    except Exception as e:
        logging.error(f"Failed to save positions: {e}")

def load_positions():
    global positions
    if os.path.exists(POSITIONS_FILE):
        try:
            with open(POSITIONS_FILE, "r") as f:
                positions = json.load(f)
            logging.info("✅ Positions loaded.")
        except Exception as e:
            positions = {}
            logging.error(f"Failed to load positions: {e}")
    else:
        positions = {}

def save_auto_trade_seen():
    try:
        with open(AUTO_TRADE_SEEN_FILE, "w") as f:
            json.dump(list(auto_trade_seen), f)
        logging.info("✅ Auto trade seen set saved.")
    except Exception as e:
        logging.error(f"Failed to save auto trade seen set: {e}")

def load_auto_trade_seen():
    global auto_trade_seen
    if os.path.exists(AUTO_TRADE_SEEN_FILE):
        try:
            with open(AUTO_TRADE_SEEN_FILE, "r") as f:
                auto_trade_seen = set(json.load(f))
            logging.info("✅ Auto trade seen set loaded.")
        except Exception as e:
            auto_trade_seen = set()
            logging.error(f"Failed to load auto trade seen set: {e}")
    else:
        auto_trade_seen = set()

# --- Copy-trading sniper wallets ---
async def run_copy_trader_loop():
    logging.info("🔁 Copy-trader loop started.")
    async with aiohttp.ClientSession() as session:
        while True:
            for wallet in WATCHED_WALLETS:
                url = f"https://api.pump.fun/wallet/{wallet}"
                try:
                    async with session.get(url, timeout=10) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            current_mints = {item['mint'] for item in data.get("tokens", [])}
                            prev_mints = wallet_token_cache.get(wallet, set())
                            new_tokens = current_mints - prev_mints
                            for mint in new_tokens:
                                await send_telegram_message(f"🧠 Copying sniper: {wallet}\nToken: {mint}")
                                try:
                                    success, tx = await execute_buy(mint, amount_usd=5)
                                    if success:
                                        price = await get_token_price(mint)
                                        positions[mint] = {
                                            "buy_price": price,
                                            "tx": tx,
                                            "timestamp": time.time()
                                        }
                                        save_positions()
                                        await send_telegram_message(f"✅ Bought: {mint} at ${price:.4f}\nTx: {tx}")
                                    else:
                                        await send_telegram_message(f"❌ Copy failed for {mint}")
                                except Exception as e:
                                    await send_telegram_message(f"❌ Copy error for {mint}: {e}")
                            wallet_token_cache[wallet] = current_mints
                            save_cache()
                        elif resp.status == 404:
                            logging.info(f"Wallet {wallet} not tracked (404).")
                except Exception as e:
                    await send_telegram_message(f"❌ Error fetching {wallet}: {e}")
            await asyncio.sleep(15)

# --- Auto trading logic: scan and buy new tokens from Raydium ---
async def scan_raydium():
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(AUTO_TRADE_API, timeout=10) as resp:
                if resp.status == 200:
                    return await resp.json()
                else:
                    logging.warning(f"Raydium API returned status {resp.status}")
        except Exception as e:
            logging.error(f"Error fetching Raydium pools: {e}")
    return []

async def run_auto_trader():
    logging.info("🤖 Auto-trader loop started.")
    await asyncio.sleep(2)  # Let other coroutines load state
    while True:
        try:
            pools = await scan_raydium()
            for pool in pools:
                mint = pool.get("baseMint")
                try:
                    liquidity = float(pool.get("liquidity", 0))
                    volume_24h = float(pool.get("volume24h", 0))
                except Exception as e:
                    logging.error(f"Error parsing pool data for {mint}: {e}")
                    continue

                if not mint or mint in auto_trade_seen or mint in positions:
                    continue
                # --- Your trading criteria here ---
                if liquidity >= 10 and volume_24h >= 10:
                    logging.info(f"🚀 Raydium auto-buying: {mint}")
                    await send_telegram_message(f"🚀 Raydium Auto-buy: {mint}\nLP: {liquidity}, 24h Volume: {volume_24h}")
                    try:
                        success, tx = await execute_buy(mint, amount_usd=5)
                        if success:
                            price = await get_token_price(mint)
                            positions[mint] = {
                                "buy_price": price,
                                "tx": tx,
                                "timestamp": time.time()
                            }
                            save_positions()
                            await send_telegram_message(f"✅ Raydium Bought: {mint} at ${price:.4f}\nTx: {tx}")
                            auto_trade_seen.add(mint)
                            save_auto_trade_seen()
                        else:
                            await send_telegram_message(f"❌ Raydium Buy failed: {mint}")
                    except Exception as e:
                        logging.error(f"Error buying {mint}: {e}")
                        await send_telegram_message(f"❌ Raydium Error buying {mint}: {e}")
                else:
                    logging.info(f"Skipping {mint}: LP={liquidity}, 24h Volume={volume_24h}")
        except Exception as e:
            logging.error(f"Error in auto-trader loop: {e}")
        await asyncio.sleep(10)

# --- Auto-sell logic: Sell at 2x ---
async def monitor_positions_and_sell():
    load_positions()
    logging.info("📈 Position monitor started.")
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
            save_positions()
        await asyncio.sleep(60)

# --- Entrypoint ---
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    logging.info("🚀 Starting combined sniper + auto-trader bot...")
    load_cache()
    load_positions()
    load_auto_trade_seen()
    try:
        async def main():
            await asyncio.gather(
                run_copy_trader_loop(),
                run_auto_trader(),
                monitor_positions_and_sell()
            )
        asyncio.run(main())
    except Exception as e:
        logging.critical(f"🔥 FATAL: Bot crashed at startup: {e}", exc_info=True)
    finally:
        save_cache()
        save_positions()
        save_auto_trade_seen()
