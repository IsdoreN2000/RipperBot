import asyncio
import logging
import aiohttp
import json
import os
from solana.rpc.async_api import AsyncClient
from utils import execute_buy, send_telegram_message

WATCHED_WALLETS = [
    "Fg6PaFpoGXkYsidMpWTK6W2BeZ7FEfcYkgS3oG2j7pDn",  # example
    # Add more sniper wallet addresses here
]

CACHE_FILE = "wallet_token_cache.json"
wallet_token_cache = {}

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

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

def save_cache():
    try:
        with open(CACHE_FILE, "w") as f:
            json.dump({k: list(v) for k, v in wallet_token_cache.items()}, f)
        logging.info("✅ Token cache saved.")
    except Exception as e:
        logging.error(f"Failed to save token cache: {e}")

async def run_copy_trader_loop():
    """
    Monitors sniper wallets and copies new token buys.
    """
    load_cache()
    async with AsyncClient("https://api.mainnet-beta.solana.com") as client:
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
                                                success, tx = await execute_buy(client, mint)
                                                if success:
                                                    await send_telegram_message(f"✅ Copied buy: {mint}\nTx: {tx}")
                                                else:
                                                    await send_telegram_message(f"❌ Copy failed for {mint}: Unknown error")
                                            except Exception as e:
                                                logging.error(f"Copy failed for {mint}: {e}")
                                                await send_telegram_message(f"❌ Copy failed for {mint}: {e}")
                                    wallet_token_cache[wallet] = current_mints
                                    save_cache()
                                else:
                                    logging.warning(f"Failed to fetch wallet {wallet}: HTTP {resp.status}")
                        except Exception as e:
                            logging.error(f"Error fetching wallet {wallet}: {e}")
                            await send_telegram_message(f"❌ Error fetching wallet {wallet}: {e}")
                except Exception as e:
                    logging.error(f"[Copy Trader Error]: {e}")
                    await send_telegram_message(f"❌ Copy trader loop error: {e}")

                await asyncio.sleep(15)

if __name__ == "__main__":
    try:
        asyncio.run(run_copy_trader_loop())
    except Exception as e:
        logging.critical(f"🔥 FATAL: Bot crashed at startup: {e}", exc_info=True)
        save_cache()
