import asyncio
import logging
import aiohttp
from solana.rpc.async_api import AsyncClient
from utils import execute_buy, send_telegram_message

# --- Add sniper wallets to watch ---
WATCHED_WALLETS = [
    "Fg6PaFpoGXkYsidMpWTK6W2BeZ7FEfcYkgS3oG2j7pDn",  # example
    # Add more sniper wallet addresses here
]

# --- Store tokens already seen ---
wallet_token_cache = {}

# --- Monitor tokens and copy trades ---
async def run_copy_trader_loop():
    logging.basicConfig(level=logging.INFO)
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

                                    # Detect new mints
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
                                else:
                                    logging.warning(f"Failed to fetch wallet {wallet}: HTTP {resp.status}")
                        except Exception as e:
                            logging.error(f"Error fetching wallet {wallet}: {e}")
                            await send_telegram_message(f"❌ Error fetching wallet {wallet}: {e}")
                except Exception as e:
                    logging.error(f"[Copy Trader Error]: {e}")
                    await send_telegram_message(f"❌ Copy trader loop error: {e}")

                await asyncio.sleep(15)  # Check every 15 seconds

if __name__ == "__main__":
    asyncio.run(run_copy_trader_loop())
