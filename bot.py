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
import requests

logging.basicConfig(level=logging.INFO)

print("=== BOT.PY STARTED ===")  # Confirm script is running

# Load environment variables
RPC_URL = os.getenv("RPC_URL", "https://mainnet.helius-rpc.com/?api-key=" + os.getenv("HELIUS_API_KEY"))
PRIVATE_KEY = json.loads(os.getenv("PRIVATE_KEY"))
keypair = Keypair.from_bytes(bytes(PRIVATE_KEY))

BUY_AMOUNT_SOL = float(os.getenv("BUY_AMOUNT_SOL", 0.1))
SLIPPAGE = float(os.getenv("SLIPPAGE", 3))
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
HELIUS_API_KEY = os.getenv("HELIUS_API_KEY")
HELIUS_URL = f"https://mainnet.helius-rpc.com/?api-key={HELIUS_API_KEY}"
PUMP_PROGRAM_ID = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
JUPITER_API_URL = "https://quote-api.jup.ag/v1/quote"

# === HELIUS TX FETCHING ===
def get_recent_signatures(limit=10):
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "getSignaturesForAddress",
        "params": [PUMP_PROGRAM_ID, {"limit": limit}]
    }
    try:
        response = requests.post(HELIUS_URL, json=payload)
        response.raise_for_status()
        result = response.json()
        print("DEBUG: getSignaturesForAddress result:", result)
        return [tx["signature"] for tx in result.get("result", [])]
    except Exception as e:
        print("DEBUG: Exception in get_recent_signatures:", e)
        logging.warning(f"Failed to fetch signatures: {e}")
        return []

def get_token_mints_from_tx(signature):
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "getTransaction",
        "params": [signature, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}]
    }
    try:
        response = requests.post(HELIUS_URL, json=payload)
        response.raise_for_status()
        result = response.json()
        print(f"DEBUG: getTransaction result for {signature}:", result)
        tx = result.get("result", {}).get("transaction", {})
        meta = result.get("result", {}).get("meta", {})
        mints = set()

        for bal in meta.get("preTokenBalances", []) + meta.get("postTokenBalances", []):
            if "mint" in bal:
                mints.add(bal["mint"])

        for instr in tx.get("message", {}).get("instructions", []):
            if "parsed" in instr and "info" in instr["parsed"]:
                info = instr["parsed"]["info"]
                if "mint" in info:
                    mints.add(info["mint"])

        for inner in meta.get("innerInstructions", []):
            for instr in inner.get("instructions", []):
                if "parsed" in instr and "info" in instr["parsed"]:
                    info = instr["parsed"]["info"]
                    if "mint" in info:
                        mints.add(info["mint"])

        return list(mints)
    except Exception as e:
        print(f"DEBUG: Exception in get_token_mints_from_tx for {signature}:", e)
        logging.warning(f"Failed to parse tx {signature}: {e}")
        return []

async def fetch_recent_tokens(limit=10):
    signatures = get_recent_signatures(limit)
    if not signatures:
        print("DEBUG: No signatures found from get_recent_signatures.")
    all_mints = set()
    for sig in signatures:
        mints = get_token_mints_from_tx(sig)
        if not mints:
            print(f"DEBUG: No mints found in transaction {sig}.")
        all_mints.update(mints)
    if not all_mints:
        print("DEBUG: No mints found from any transaction.")
    return [{"mint": mint} for mint in all_mints]

# === BUYING & SELLING ===
async def get_swap_route(input_mint, output_mint, amount, slippage=3):
    params = {
        "inputMint": input_mint,
        "outputMint": output_mint,
        "amount": str(amount),
        "slippage": str(slippage),
        "onlyDirectRoutes": "false"  # <-- changed
    }
    async with aiohttp.ClientSession() as session:
        async with session.get(JUPITER_API_URL, params=params, timeout=30) as resp:  # <-- timeout increased
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
    await client.confirm_transaction(sig.value)
    return sig.value

async def execute_buy(mint, amount_usd=None):
    input_mint = "So11111111111111111111111111111111111111112"
    output_mint = mint
    amount = int(BUY_AMOUNT_SOL * 1_000_000_000)
    try:
        async with AsyncClient(RPC_URL) as client:
            route = await get_swap_route(input_mint, output_mint, amount, SLIPPAGE)
            sig = await execute_swap(route, client)
        return True, sig
    except Exception as e:
        logging.error(f"execute_buy failed for {mint}: {e}")
        raise

async def execute_sell(mint, multiplier=2.0):
    input_mint = mint
    output_mint = "So11111111111111111111111111111111111111112"
    amount = int(BUY_AMOUNT_SOL * multiplier * 1_000_000_000)
    async with AsyncClient(RPC_URL) as client:
        route = await get_swap_route(input_mint, output_mint, amount, SLIPPAGE)
        sig = await execute_swap(route, client)
    return True, sig

async def get_token_price(mint: str) -> float:
    url = f"https://api.pump.fun/price/{mint}"
    async with aiohttp.ClientSession() as session:
        async with session.get(url, timeout=10) as resp:
            if resp.status == 200:
                data = await resp.json()
                return float(data.get("price", 0))
            else:
                raise Exception(f"Price fetch failed for {mint}: {resp.status}")

# === TELEGRAM NOTIFICATIONS ===
async def send_telegram_message(message):
    if not TELEGRAM_TOKEN or not CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True
    }
    async with aiohttp.ClientSession() as session:
        try:
            await session.post(url, json=payload, timeout=10)
        except Exception as e:
            logging.error(f"Telegram error: {e}")

# === TOKEN FILTERING ===
def is_token_eligible(token):
    mint = token.get("mint")
    if not mint:
        return False, "Missing mint"
    return True, ""

# === MAIN LOOP ===
async def main():
    tokens = await fetch_recent_tokens(limit=10)
    logging.info(f"Recent token mints: {[t['mint'] for t in tokens]}")
    for token in tokens:
        mint = token.get("mint", "unknown")
        name = token.get("name", "unknown")
        eligible, reason = is_token_eligible(token)
        if eligible:
            try:
                success, sig = await execute_buy(mint)
                if success:
                    await send_telegram_message(f"✅ Bought {name} ({mint})\nTx: {sig}")
            except Exception as e:
                logging.error(f"Buy failed for {name} ({mint}): {e}")
        else:
            logging.info(f"{name} not eligible: {reason}")
        await asyncio.sleep(1)

if __name__ == "__main__":
    asyncio.run(main())
