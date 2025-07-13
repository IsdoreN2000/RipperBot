import asyncio
import logging
import aiohttp
from utils import execute_buy, send_telegram_message

# --- Add sniper wallets to watch ---
WATCHED_WALLETS = [
    "Fg6PaFpoGXkYsidMpWTK6W2BeZ7FEfcYkgS3oG2j7pDn",  # example
    # Add more sniper wallet addresses here
]

# --- Store tokens already seen ---
wallet_token_cache = {}

# --- Monitor tokens and copy trades ---
async def run_copy_trader_loop(client):
    """
    Monitors watched wallets for new token buys and copies the trade.
    Uses the provided Solana AsyncClient for any on-chain actions.
    """
    logging.basicConfig(level=logging.INFO)
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
                                            # Example: you can use `client` here for on-chain actions if needed
                                            # e.g., balance = await client.get_balance(Pubkey.from_string(wallet))
                                            success, tx = await execute_buy(mint)
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

# If you want to test this script standalone, you can use the following:
# (Uncomment and adjust as needed)
#
# if __name__ == "__main__":
#     from solana.rpc.async_api import AsyncClient
#     async def main():
#         async with AsyncClient("https://api.mainnet-beta.solana.com") as client:
#             await run_copy_trader_loop(client)
#     asyncio.run(main())
