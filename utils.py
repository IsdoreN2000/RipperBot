import aiohttp
import os
import json
from datetime import datetime, timezone
import asyncio

from solders.keypair import Keypair
from solders.pubkey import Pubkey
from solana.rpc.async_api import AsyncClient
from solana.rpc.types import TxOpts

# --- Configuration ---
RPC_URL = os.getenv("RPC_URL", "https://api.mainnet-beta.solana.com")

private_key_env = os.getenv("PRIVATE_KEY")
if private_key_env is None:
    raise EnvironmentError("PRIVATE_KEY environment variable is not set.")
PRIVATE_KEY = json.loads(private_key_env)

BUY_AMOUNT_SOL = float(os.getenv("BUY_AMOUNT_SOL", 0.1))
SLIPPAGE = float(os.getenv("SLIPPAGE", 3))

keypair = Keypair.from_bytes(bytes(PRIVATE_KEY))

# --- Placeholder: Implement your actual buy txn creation logic ---
async def create_buy_txn(*args, **kwargs):
    raise NotImplementedError("Buy transaction logic not implemented yet.")

# --- Placeholder: Implement your actual sell txn creation logic ---
async def create_sell_txn(*args, **kwargs):
    raise NotImplementedError("Sell transaction logic not implemented yet.")

# --- Fetch recent tokens ---
async def fetch_recent_tokens():
    url = "https://api.pump.fun/tokens?sort=recent"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            if resp.status == 200:
                tokens = await resp.json()
                print(f"[DEBUG] Fetched {len(tokens)} tokens")
                return tokens
            else:
                print(f"[DEBUG] Failed to fetch tokens, status: {resp.status}")
                return []

# --- Token eligibility filter ---
def is_token_eligible(token):
    try:
        age = datetime.now(timezone.utc).timestamp() - int(token.get("timestamp", 0))
        liquidity = float(token.get("liquidity", 0))
        holders = int(token.get("uniqueHolders", 0))

        print(f"[DEBUG] Token {token.get('mint', 'unknown')} - Age: {age:.2f}s, Liquidity: {liquidity}, Holders: {holders}")

        if age < 1 or age > 180:
            print("[DEBUG] Filter reject: Token age not within 1s to 3min range")
            return False, "Token age not within 1s to 3min range"
        if liquidity < 0.3:
            print("[DEBUG] Filter reject: Low liquidity")
            return False, "Low liquidity"
        if holders < 2:
            print("[DEBUG] Filter reject: Not enough holders")
            return False, "Not enough holders"

        print("[DEBUG] Token passed filters")
        return True, ""
    except Exception as e:
        print(f"[DEBUG] Filter error: {e}")
        return False, f"Error in filter: {e}"

# --- Execute buy (placeholder) ---
async def execute_buy(client, mint):
    try:
        txn = await create_buy_txn(client, keypair, Pubkey.from_string(mint), BUY_AMOUNT_SOL, SLIPPAGE)
        sig = await client.send_raw_transaction(txn.serialize(), opts=TxOpts(skip_preflight=True))
        return True, str(sig.value)
    except Exception as e:
        print("Buy failed:", e)
        return False, None

# --- Execute sell (placeholder) ---
async def execute_sell(client, mint, multiplier=2.0):
    try:
        txn = await create_sell_txn(client, keypair, Pubkey.from_string(mint), multiplier)
        sig = await client.send_raw_transaction(txn.serialize(), opts=TxOpts(skip_preflight=True))
        return True, str(sig.value)
    except Exception as e:
        print("Sell failed:", e)
        return False, None

# --- Telegram notification ---
async def send_telegram_message(message):
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        print("[DEBUG] Telegram credentials not set.")
        return
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True
    }
    async with aiohttp.ClientSession() as session:
        await session.post(url, json=payload)

# --- Main async loop ---
async def main():
    async with AsyncClient(RPC_URL) as client:
        tokens = await fetch_recent_tokens()
        for token in tokens:
            eligible, reason = is_token_eligible(token)
            if eligible:
                print(f"Eligible token: {token['mint']}")
                await send_telegram_message(
                    f"Eligible token: `{token['mint']}`\nLiquidity: {token.get('liquidity')}\nHolders: {token.get('uniqueHolders')}"
                )
                # Uncomment below when buy logic is implemented
                # success, tx_sig = await execute_buy(client, token['mint'])
                # if success:
                #     await send_telegram_message(f"Bought token {token['mint']}! Tx: {tx_sig}")
            else:
                print(f"Token {token.get('mint', 'unknown')} not eligible: {reason}")

if __name__ == "__main__":
    asyncio.run(main())
