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
from dotenv import load_dotenv

load_dotenv()

# === Config ===
logging.basicConfig(level=logging.INFO)
HELIUS_API_KEY = os.getenv("HELIUS_API_KEY")
if not HELIUS_API_KEY:
    raise EnvironmentError("❌ HELIUS_API_KEY is not set in environment variables.")
HELIUS_URL = f"https://mainnet.helius-rpc.com/?api-key={HELIUS_API_KEY}"

PRIVATE_KEY = json.loads(os.getenv("PRIVATE_KEY", "[]"))
if not PRIVATE_KEY:
    raise EnvironmentError("❌ PRIVATE_KEY is not set in environment variables.")
keypair = Keypair.from_bytes(bytes(PRIVATE_KEY))

BUY_AMOUNT_SOL = float(os.getenv("BUY_AMOUNT_SOL", 0.1))
SLIPPAGE = float(os.getenv("SLIPPAGE", 3))
JUPITER_API_URL = "https://quote-api.jup.ag/v1/quote"

POSITIONS_FILE = "positions.json"
positions = {}

def save_positions():
    try:
        with open(POSITIONS_FILE, "w") as f:
            json.dump(positions, f)
    except Exception as e:
        logging.error(f"Failed to save positions: {e}")

def load_positions():
    global positions
    if os.path.exists(POSITIONS_FILE):
        try:
            with open(POSITIONS_FILE, "r") as f:
                positions = json.load(f)
        except Exception as e:
            logging.error(f"Failed to load positions: {e}")
            positions = {}

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
    try:
        timestamp = int(token.get("timestamp", 0))
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
    input_mint = "So11111111111111111111111111111111111111112"
    output_mint = mint
    amount = int(BUY_AMOUNT_SOL * 1_000_000_000)
    async with AsyncClient(HELIUS_URL) as client:
        try:
            route = await get_swap_route(input_mint, output_mint, amount, SLIPPAGE)
            sig = await execute_swap(route, client)
            return True, sig
        except Exception as e:
            logging.error(f"Buy failed for {mint}: {e}")
            return False, str(e)

async def execute_sell(mint, multiplier=2.0):
    input_mint = mint
    output_mint = "So11111111111111111111111111111111111111112"
    amount = int(BUY_AMOUNT_SOL * multiplier * 1_000_000_000)
    async with AsyncClient(HELIUS_URL) as client:
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
    load_positions()
    tokens = await fetch_recent_tokens()
    for token in tokens:
        name = token.get("name", "unknown")
        mint = token.get("mint")
        eligible, reason = is_token_eligible(token)
        if eligible and mint not in positions:
            try:
                success, sig = await execute_buy(mint)
                if success:
                    price = await get_token_price(mint)
                    positions[mint] = {
                        "buy_price": price,
                        "tx": sig,
                        "timestamp": datetime.now(timezone.utc).timestamp()
                    }
                    save_positions()
                    await send_telegram_message(f"Bought {name} ({mint}) at ${price:.4f}\nTx: {sig}")
            except Exception as e:
                logging.error(f"Buy failed for {name}: {e}")
        else:
            logging.info(f"{name} not eligible: {reason}")
        await asyncio.sleep(1)  # Optional: avoid rate limits

async def monitor_positions_and_sell():
    while True:
        to_remove = []
        for mint, data in positions.items():
            try:
                buy_price = float(data["buy_price"])
                current_price = await get_token_price(mint)
                if current_price >= buy_price * 2:
                    await send_telegram_message(f"Selling {mint} at 2x: ${current_price:.4f}")
                    success, tx = await execute_sell(mint)
                    if success:
                        await send_telegram_message(f"Sold {mint}\nTx: {tx}")
                        to_remove.append(mint)
                    else:
                        await send_telegram_message(f"Sell failed for {mint}")
            except Exception as e:
                logging.error(f"Sell check failed for {mint}: {e}")
        for mint in to_remove:
            positions.pop(mint, None)
        if to_remove:
            save_positions()
        await asyncio.sleep(60)  # Check every minute

if __name__ == "__main__":
    load_positions()
    try:
        async def runner():
            await asyncio.gather(
                main(),
                monitor_positions_and_sell()
            )
        asyncio.run(runner())
    except Exception as e:
        logging.critical(f"Bot crashed: {e}", exc_info=True)
        save_positions()
