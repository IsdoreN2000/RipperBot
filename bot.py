import os
import json
import base64
import aiohttp
import logging
from datetime import datetime, timezone
from solders.keypair import Keypair
from solders.transaction import VersionedTransaction
from solana.rpc.async_api import AsyncClient
from solana.rpc.types import TxOpts
import asyncio

logging.basicConfig(level=logging.INFO)

# --- Load from .env or default
HELIUS_API_KEY = os.getenv("HELIUS_API_KEY")
if not HELIUS_API_KEY:
    raise EnvironmentError("❌ HELIUS_API_KEY is not set in environment variables.")

RPC_URL = f"https://mainnet.helius-rpc.com/?api-key={HELIUS_API_KEY}"

private_key_env = os.getenv("PRIVATE_KEY")
if private_key_env is None:
    raise EnvironmentError("PRIVATE_KEY environment variable is not set.")
PRIVATE_KEY = json.loads(private_key_env)
keypair = Keypair.from_bytes(bytes(PRIVATE_KEY))

BUY_AMOUNT_SOL = float(os.getenv("BUY_AMOUNT_SOL", 0.1))
SLIPPAGE = float(os.getenv("SLIPPAGE", 3))
JUPITER_API_URL = "https://quote-api.jup.ag/v1/quote"

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

def is_token_eligible(token):
    """
    Checks if a token meets age, liquidity, and holder requirements.
    """
    try:
        timestamp = int(token.get("timestamp", 0))
        # Handle ms or s
        if timestamp > 1e12:
            timestamp = timestamp // 1000
        age = datetime.now(timezone.utc).timestamp() - timestamp
        liquidity = float(token.get("liquidity", 0))
        holders = int(token.get("uniqueHolders", 0))

        logging.info(
            f"Token {token.get('mint', 'unknown')} - "
            f"Name: {token.get('name', 'unknown')} - "
            f"Age: {age:.2f}s, Liquidity: {liquidity}, Holders: {holders}"
        )

        if age < 1 or age > 180:
            return False, "Age not in range"
        if liquidity < 0.3:
            return False, "Low liquidity"
        if holders < 2:
            return False, "Too few holders"
        return True, ""
    except Exception as e:
        return False, str(e)

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
                raise Exception(f"Jupiter error: {resp.status}")
            data = await resp.json()
            routes = data.get("data")
            if not routes or "swapTransaction" not in routes[0]:
                raise Exception("No route or swapTransaction found")
            return routes[0]

async def execute_swap(route, client):
    txn_b64 = route['swapTransaction']
    txn_bytes = base64.b64decode(txn_b64)
    txn = VersionedTransaction.deserialize(txn_bytes)
    txn.sign([keypair])
    sig = await client.send_raw_transaction(txn.serialize(), opts=TxOpts(skip_preflight=True))
    if not sig or not sig.value:
        raise Exception("Transaction failed to send")
    await client.confirm_transaction(sig.value)
    return sig.value

async def execute_buy(mint, amount_usd=None):
    """
    Executes a buy swap for the given mint.
    """
    input_mint = "So11111111111111111111111111111111111111112"
    output_mint = mint
    amount = int(BUY_AMOUNT_SOL * 1_000_000_000)
    async with AsyncClient(RPC_URL) as client:
        try:
            route = await get_swap_route(input_mint, output_mint, amount, SLIPPAGE)
            sig = await execute_swap(route, client)
            return True, sig
        except Exception as e:
            logging.error(f"Buy failed for {mint}: {e}")
            return False, str(e)

async def execute_sell(mint, multiplier=2.0):
    """
    Executes a sell swap for the given mint.
    """
    input_mint = mint
    output_mint = "So11111111111111111111111111111111111111112"
    amount = int(BUY_AMOUNT_SOL * multiplier * 1_000_000_000)
    async with AsyncClient(RPC_URL) as client:
        try:
            route = await get_swap_route(input_mint, output_mint, amount, SLIPPAGE)
            sig = await execute_swap(route, client)
            return True, sig
        except Exception as e:
            logging.error(f"Sell failed for {mint}: {e}")
            return False, str(e)

async def get_token_price(mint: str) -> float:
    url = f"https://api.pump.fun/price/{mint}"
    async with aiohttp.ClientSession() as session:
        async with session.get(url, timeout=10) as resp:
            if resp.status == 200:
                data = await resp.json()
                return float(data.get("price", 0))
            else:
                raise Exception(f"Price fetch failed for {mint}: {resp.status}")

async def send_telegram_message(message):
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
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
            logging.error(f"Telegram error: {e}")

async def main():
    tokens = await fetch_recent_tokens()
    for token in tokens:
        name = token.get("name", "unknown")
        eligible, reason = is_token_eligible(token)
        if eligible:
            try:
                success, sig = await execute_buy(token.get("mint"))
                if success:
                    await send_telegram_message(f"Bought {name} ({token.get('mint')})\nTx: {sig}")
            except Exception as e:
                logging.error(f"Buy failed for {name}: {e}")
        else:
            logging.info(f"{name} not eligible: {reason}")
        await asyncio.sleep(1)  # Optional: avoid rate limits

if __name__ == "__main__":
    asyncio.run(main())
