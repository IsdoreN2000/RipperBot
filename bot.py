import asyncio
import logging
import aiohttp
import json
import signal
import sys
from typing import Dict, Set

from utils import execute_buy, send_telegram_message
from solana.rpc.async_api import AsyncClient

# --- Configure logging globally ---
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# --- Add sniper wallets to watch (REAL) ---
WATCHED_WALLETS = [
    "8CKfrsQkdrkwyZpXVPXTqBo37Ep5dWq2UKR7o2L3TfVu",  # SniperAlpha
    "Dj8v6HkSSQ8j2RWkLq8Dw4xZ5XPq6pEGpEV9nPUqtrzU",  # CopyLoopX
    "GZ6PEx2R3GqmvUw8EWEAxEA5etC7mDAv4aHaKq2RY1nD"   # BigBagsBot
]

# --- Store tokens already seen (wallet -> set of mints) ---
wallet_token_cache: Dict[str, Set[str]] = {}

CACHE_FILE = "token_cache.json"

def save_cache():
    """Persist the wallet_token_cache to disk."""
    try:
        with open(CACHE_FILE, "w") as f:
            json.dump({k: list(v) for k, v in wallet_token_cache.items()}, f)
        logging.info("✅ Token cache saved.")
    except Exception as e:
        logging.error(f"Failed to save token cache: {e}")

def load_cache():
    """Load the wallet_token_cache from disk."""
    global wallet_token_cache
    try:
        with open(CACHE_FILE, "r") as f:
            wallet_token_cache = {k: set(v) for k, v in json.load(f).items()}
        logging.info("✅ Token cache loaded.")
    except FileNotFoundError:
        wallet_token_cache = {}
        logging.info("No existing token cache found. Starting fresh.")
    except Exception as e:
        wallet_token_cache = {}
        logging.error(f"Failed to load token cache: {e}")

def setup_signal_handlers():
    """Ensure cache is saved on shutdown."""
    def handle_exit(sig, frame):
        logging.info(f"Received {sig.name}, saving cache and exiting...")
        save_cache()
        sys.exit(0)
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, handle_exit)

async def run_copy_trader_loop(client: AsyncClient):
    """Main loop: monitors watched wallets and copies new token buys."""
    logging.info("🔁 Copy-trader loop started.")
    async with aiohttp.ClientSession() as session:
        while True:
            try:
                for wallet in WATCHED_WALLETS:
                    url = f"https://api.pump.fun/wallet/{wallet}"
                    try:
                        async with session.get(url, timeout=10) as resp:
                            if resp.status == 200:
                                data = await resp.json()
                                current_mints = {item['mint'] for item in data.get("tokens", [])}
                                prev_mints = wallet_token_cache.get(wallet, set())

                                new_tokens = current_mints - prev_mints
                                if new_tokens:
                                    for mint in new_tokens:
                                        await send_telegram_message(f"🧠 Copying sniper: {wallet}\nToken: {mint}")
                                        try:
                                            success, tx = await execute_buy(mint)
                                            if success:
                                                await send_telegram_message(f"✅ Copied buy: {mint}\nTx: {tx}")
                                            else:
                                                await send_telegram_message(f"❌ Copy failed for {mint}: Unknown error")
                                        except Exception as e:
                                            logging.error(f"Copy failed for {mint}: {e}")
                                            await send_telegram_message(f"❌ Copy failed for {mint}: {e}")
                                wallet_token_cache[wallet] = current_mints
                                save_cache()
                            elif resp.status == 404:
                                logging.info(f"Wallet {wallet} not tracked on pump.fun (no current tokens).")
                            else:
                                logging.warning(f"Failed to fetch wallet {wallet}: HTTP {resp.status}")
                    except Exception as e:
                        logging.error(f"Error fetching wallet {wallet}: {e}")
                        await send_telegram_message(f"❌ Error fetching wallet {wallet}: {e}")
            except Exception as e:
                logging.error(f"[Copy Trader Error]: {e}")
                await send_telegram_message(f"❌ Copy trader loop error: {e}")

            await asyncio.sleep(15)

async def resilient_copy_trader(client: AsyncClient):
    """Runs the copy trader loop, restarting on error with notification."""
    while True:
        try:
            await run_copy_trader_loop(client)
        except Exception as e:
            logging.critical(f"🔥 Copy trader crashed: {e}", exc_info=True)
            await send_telegram_message(f"🔥 Copy trader crashed: {e}")
            await asyncio.sleep(60)  # Wait before retrying

if __name__ == "__main__":
    logging.info("🚀 Starting sniper bot...")
    load_cache()
    setup_signal_handlers()  # No event loop argument needed
    try:
        async def main():
            async with AsyncClient("https://api.mainnet-beta.solana.com") as client:
                await resilient_copy_trader(client)
        asyncio.run(main())
    except Exception as e:
        logging.critical(f"🔥 FATAL: Bot crashed at startup: {e}", exc_info=True)
    finally:
        save_cache()
