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
        return [tx["signature"] for tx in result.get("result", [])]
    except Exception as e:
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
        logging.warning(f"Failed to parse tx {signature}: {e}")
        return []

async def fetch_recent_tokens(limit=10):
    signatures = get_recent_signatures(limit)
    all_mints = set()
    for sig in signatures:
        mints = get_token_mints_from_tx(sig)
        all_mints.update(mints)
    return [{"mint": mint} for mint in all_mints]

# === LIQUIDITY CHECK ===
async def has_liquidity(mint):
    input_mint = "So11111111111111111111111111111111111111112"
    output_mint = mint
    amount = int(BUY_AMOUNT_SOL * 1_000_000_000)
    params = {
        "inputMint": input_mint,
        "outputMint": output_mint,
        "amount": str(amount),
        "slippage": str(SLIPPAGE),
        "onlyDirectRoutes": "true"
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(JUPITER_API_URL, params=params, timeout=20) as resp:
                if resp.status != 200:
                    return False
                data = await resp.json()
                return bool(data.get("data"))
    except Exception as e:
        logging.warning(f"Liquidity check failed for {mint}: {e}")
        return False

# === BUYING & SELLING ===
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
    await client.confirm_transaction(sig.value)
    return sig.value

async def execute_buy(mint):
    input_mint = "So11111111111111111111111111111111111111112"
    output_mint = mint
    amount = int(BUY_AMOUNT_SOL * 1_000_000_000)
    async with AsyncClient(RPC_URL) as client:
        route = await get_swap_route(input_mint, output_mint, amount, SLIPPAGE)
        sig = await execute_swap(route, client)
    return True, sig

# === TELEGRAM ===
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

# === TOKEN FILTER ===
def is_token_eligible(token):
    mint = token.get("mint")
    if not mint or mint == "So11111111111111111111111111111111111111112":
        return False, "Missing or invalid mint"
    return True, ""

# === MAIN LOOP ===
async def main():
    tokens = await fetch_recent_tokens(limit=10)
    logging.info(f"Recent token mints: {[t['mint'] for t in tokens]}")
    for token in tokens:
        mint = token.get("mint")
        eligible, reason = is_token_eligible(token)
        if not eligible:
            logging.info(f"Skipped token {mint}: {reason}")
            continue

        if not await has_liquidity(mint):
            logging.info(f"Skipped token {mint}: No liquidity pool found.")
            await asyncio.sleep(0.5)
            continue

        logging.info(f"Attempting to buy token {mint} for {BUY_AMOUNT_SOL} SOL...")
        try:
            success, sig = await execute_buy(mint)
            if success:
                await send_telegram_message(f"✅ Bought {mint}\nTx: {sig}")
        except Exception as e:
            logging.error(f"execute_buy failed for {mint}: {e}")

        await asyncio.sleep(0.5)

if __name__ == "__main__":
    asyncio.run(main())
