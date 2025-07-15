import asyncio
import logging
import aiohttp
import json
import os
from solana.rpc.async_api import AsyncClient
from utils import execute_buy, send_telegram_message

# --- Configuration ---
WATCHED_WALLETS = [
    "DfMxre4cKmvogbLrPigxmibVTTQDuzjdXojWzjCXXhzj",
    "4DdrfiDHpmx55i4SPssxVzS9ZaKLb8qr45NKY9Er9nNh",
    "Hnnw2hAgPgGiFKouRWvM3fSk3HnYgRv4Xq1PjUEBEuWM",
    # Add more sniper wallets here if needed
]

CACHE_FILE = "wallet_token_cache.json"
wallet_token_cache = {}

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# --- Token Cache Handling ---
def load_cache():
    global wallet_token_cache
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r") as f:
                wallet_token_cache = {k: set(v) for k, v in json.load(f).items()}
            logging.info("✅ Token cache loaded.")
        except Exception as e:
            logging.error(f"Failed to load token cache: {e}")
            wallet_token_cache = {}
    else:
        wallet_token_cache = {wallet: set() for wallet in WATCHED_WALLETS}

def save_cache():
    try:
        with open(CACHE_FILE, "w") as f:
            json.dump({k: list(v) for k, v in wallet_token_cache.items()}, f)
        logging.info("✅ Token cache saved.")
    except Exception as e:
        logging.error(f"Failed to save token cache: {e}")

# --- Copy Trading Logic ---
async def run_copy_trader_loop():
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
                                    previous_mints = wallet_token_cache.get(wallet, set())

                                    new_tokens = current_mints - previous_mints
                                    if new_tokens:
                                        for mint in new_tokens:
                                            await send_telegram_message(f"🧠 Copying sniper wallet:\n{wallet}\nToken: {mint}")
                                            try:
                                                success, tx = await execute_buy(mint)
                                                if success:
                                                    await send_telegram_message(f"✅ Copied buy for {mint}\nTx: {tx}")
                                                else:
                                                    await send_telegram_message(f"❌ Copy failed for {mint}: Unknown reason")
                                            except Exception as e:
                                                logging.error(f"Buy failed for {mint}: {e}")
                                                await send_telegram_message(f"❌ Copy failed for {mint}: {e}")
                                    wallet_token_cache[wallet] = current_mints
                                    save_cache()
                                else:
                                    logging.warning(f"Pump.fun API error for wallet {wallet}: HTTP {resp.status}")
                        except Exception as e:
                            logging.error(f"Wallet fetch error [{wallet}]: {e}")
                            await send_telegram_message(f"❌ Error fetching wallet {wallet}: {e}")
                except Exception as e:
                    logging.error(f"[Copy Trader Error]: {e}")
                    await send_telegram_message(f"❌ Copy trader loop error: {e}")

                await asyncio.sleep(15)

# --- Entrypoint ---
if __name__ == "__main__":
    try:
        asyncio.run(run_copy_trader_loop())
    except Exception as e:
        logging.critical(f"🔥 FATAL: Bot crashed at startup: {e}", exc_info=True)
        save_cache()
