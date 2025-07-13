import os
import json
import base64
import aiohttp
import asyncio
import logging
from datetime import datetime, timezone
from solders.keypair import Keypair
from solders.transaction import VersionedTransaction
from solana.rpc.async_api import AsyncClient
from solana.rpc.types import TxOpts

# --- Configuration ---
logging.basicConfig(level=logging.INFO)
RPC_URL = os.getenv("RPC_URL", "https://api.mainnet-beta.solana.com")

private_key_env = os.getenv("PRIVATE_KEY")
if private_key_env is None:
    raise EnvironmentError("PRIVATE_KEY environment variable is not set.")
PRIVATE_KEY = json.loads(private_key_env)
keypair = Keypair.from_bytes(bytes(PRIVATE_KEY))

BUY_AMOUNT_SOL = float(os.getenv("BUY_AMOUNT_SOL", 0.1))
SLIPPAGE = float(os.getenv("SLIPPAGE", 3))
JUPITER_API_URL = "https://quote-api.jup.ag/v1/quote"

# --- Fetch recent tokens ---
async def fetch_recent_tokens():
    url = "https://api.pump.fun/tokens?sort=recent"
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url, timeout=10) as resp:
                if resp.status == 200:
                    tokens = await resp.json()
                    logging.info(f"Fetched {len(tokens)} tokens")
                    return tokens
                else:
                    logging.warning(f"Failed to fetch tokens, status: {resp.status}")
                    return []
        except Exception as e:
            logging.error(f"Error fetching tokens: {e}")
            return []

# --- Token eligibility filter ---
def is_token_eligible(token):
    try:
        age = datetime.now(timezone.utc).timestamp() - int(token.get("timestamp", 0))
        liquidity = float(token.get("liquidity", 0))
        holders = int(token.get("uniqueHolders", 0))

        logging.info(f"Token {token.get('mint', 'unknown')} - Age: {age:.2f}s, Liquidity: {liquidity}, Holders: {holders}")

        if age < 1 or age > 180:
            logging.info("Filter reject: Token age not within 1s to 3min range")
            return False, "Token age not within 1s to 3min range"
        if liquidity < 0.3:
            logging.info("Filter reject: Low liquidity")
            return False, "Low liquidity"
        if holders < 2:
            logging.info("Filter reject: Not enough holders")
            return False, "Not enough holders"

        logging.info("Token passed filters")
        return True, ""
    except Exception as e:
        logging.error(f"Filter error: {e}")
        return False, f"Error in filter: {e}"

# --- Get swap route from Jupiter ---
async def get_swap_route(input_mint, output_mint, amount, slippage=3):
    params = {
        "inputMint": input_mint,
        "outputMint": output_mint,
        "amount": str(amount),
        "slippage": str(slippage),
        "onlyDirectRoutes": "true"
    }
    async with aiohttp.ClientSession() as session:
        async with session.get(JUPITER_API_URL, params=params, timeout=10) as resp:
            if resp.status != 200:
                raise Exception(f"Jupiter API error: {resp.status}")
            data = await resp.json()
            routes = data.get("data")
            if not routes or "swapTransaction" not in routes[0]:
                raise Exception("No swap routes found or missing swapTransaction")
            return routes[0]

# --- Execute swap transaction ---
async def execute_swap(route, client):
    txn_b64 = route['swapTransaction']
    txn_bytes = base64.b64decode(txn_b64)
    txn = VersionedTransaction.deserialize(txn_bytes)
    txn.sign([keypair])
    sig = await client.send_raw_transaction(txn.serialize(), opts=TxOpts(skip_preflight=True))
    await client.confirm_transaction(sig.value)
    return sig.value

# --- Execute buy using Jupiter ---
async def execute_buy(client, mint):
    input_mint = "So11111111111111111111111111111111111111112"  # Wrapped SOL
    output_mint = mint
    amount = int(BUY_AMOUNT_SOL * 1_000_000_000)  # 1 SOL = 1_000_000_000 lamports
    route = await get_swap_route(input_mint, output_mint, amount, SLIPPAGE)
    sig = await execute_swap(route, client)
    return True, sig

# --- Execute sell using Jupiter ---
async def execute_sell(client, mint, multiplier=2.0):
    input_mint = mint
    output_mint = "So11111111111111111111111111111111111111112"  # Wrapped SOL
    amount = int(BUY_AMOUNT_SOL * multiplier * 1_000_000_000)
    route = await get_swap_route(input_mint, output_mint, amount, SLIPPAGE)
    sig = await execute_swap(route, client)
    return True, sig

# --- Telegram notification ---
async def send_telegram_message(message):
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        logging.warning("Telegram credentials not set.")
        return
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True
    }
    async with aiohttp.ClientSession() as session:
        try:
            await session.post(url, json=payload, timeout=10)
        except Exception as e:
            logging.error(f"Error sending Telegram message: {e}")

# --- Main execution flow ---
async def main():
    tokens = await fetch_recent_tokens()
    if not tokens:
        logging.info("No tokens fetched.")
        return

    for token in tokens:
        eligible, reason = is_token_eligible(token)
        if eligible:
            async with AsyncClient(RPC_URL) as client:
                try:
                    success, sig = await execute_buy(client, token["mint"])
                    if success:
                        await send_telegram_message(f"Bought token {token['mint']} - Tx: {sig}")
                    else:
                        await send_telegram_message(f"Failed to buy token {token['mint']}")
                except Exception as e:
                    logging.error(f"Error executing buy: {e}")
                    await send_telegram_message(f"Error buying token {token['mint']}: {e}")
        else:
            logging.info(f"Token {token.get('mint', 'unknown')} not eligible: {reason}")

if __name__ == "__main__":
    asyncio.run(main())
