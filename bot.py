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
import traceback

logging.basicConfig(level=logging.INFO)
print("=== BOT.PY STARTED ===")

# --- ENVIRONMENT VARIABLES ---
RPC_URL = os.getenv("RPC_URL", "https://mainnet.helius-rpc.com/?api-key=" + os.getenv("HELIUS_API_KEY"))
PRIVATE_KEY = json.loads(os.getenv("PRIVATE_KEY"))
keypair = Keypair.from_bytes(bytes(PRIVATE_KEY))
BUY_AMOUNT_SOL = float(os.getenv("BUY_AMOUNT_SOL", 0.01))
SLIPPAGE = float(os.getenv("SLIPPAGE", 3))
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
HELIUS_API_KEY = os.getenv("HELIUS_API_KEY")
HELIUS_URL = f"https://mainnet.helius-rpc.com/?api-key={HELIUS_API_KEY}"
PUMP_PROGRAM_ID = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
JUPITER_QUOTE_URL = "https://quote-api.jup.ag/v6/quote"
JUPITER_SWAP_URL = "https://quote-api.jup.ag/v6/swap"
WRAPPED_SOL = "So11111111111111111111111111111111111111112"
PROFIT_TARGET = float(os.getenv("PROFIT_TARGET", 1.5))
STOP_LOSS = float(os.getenv("STOP_LOSS", 0.8))
PRICE_CHECK_INTERVAL = int(os.getenv("PRICE_CHECK_INTERVAL", 30))

# Persistent record of bought tokens
BOUGHT_TOKENS_FILE = "bought_tokens.json"
try:
    with open(BOUGHT_TOKENS_FILE, "r") as f:
        BOUGHT_TOKENS = set(json.load(f))
except:
    BOUGHT_TOKENS = set()

# --- HELIUS TX FETCHING (ASYNC) ---
async def get_recent_signatures(limit=10):
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "getSignaturesForAddress",
        "params": [PUMP_PROGRAM_ID, {"limit": limit}]
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(HELIUS_URL, json=payload, timeout=10) as resp:
                result = await resp.json()
                return [tx["signature"] for tx in result.get("result", [])]
    except Exception as e:
        logging.warning(f"[get_recent_signatures] Failed to fetch signatures: {e}\n{traceback.format_exc()}")
        return []

async def get_token_mints_from_tx(signature):
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "getTransaction",
        "params": [signature, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}]
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(HELIUS_URL, json=payload, timeout=10) as resp:
                result = await resp.json()
                meta = result.get("result", {}).get("meta", {})
                tx = result.get("result", {}).get("transaction", {})
                mints = set()

                for bal in meta.get("preTokenBalances", []) + meta.get("postTokenBalances", []):
                    if "mint" in bal:
                        mints.add(bal["mint"])

                for instr in tx.get("message", {}).get("instructions", []):
                    if "parsed" in instr and "info" in instr["parsed"]:
                        if "mint" in instr["parsed"]["info"]:
                            mints.add(instr["parsed"]["info"]["mint"])

                for inner in meta.get("innerInstructions", []):
                    for instr in inner.get("instructions", []):
                        if "parsed" in instr and "info" in instr["parsed"]:
                            if "mint" in instr["parsed"]["info"]:
                                mints.add(instr["parsed"]["info"]["mint"])

                logging.info(f"[get_token_mints_from_tx] Mints from {signature}: {mints}")
                return list(mints)
    except Exception as e:
        logging.warning(f"[get_token_mints_from_tx] Failed to parse tx {signature}: {e}\n{traceback.format_exc()}")
        return []

# [rest of code remains unchanged]

# --- MAIN LOOP ---
async def main():
    tokens = await fetch_recent_tokens(limit=10)
    logging.info(f"[main] Recent token mints: {[t['mint'] for t in tokens]}")
    for token in tokens:
        mint = token.get("mint")
        eligible, reason = is_token_eligible(token)

        if not eligible:
            logging.info(f"[main] Skipped token {mint}: {reason}")
            continue

        if mint in BOUGHT_TOKENS:
            logging.info(f"[main] Skipped token {mint}: Already bought.")
            continue

        has_pool = await has_liquidity(mint)
        if not has_pool:
            logging.info(f"[main] Skipped token {mint}: No liquidity pool found.")
            continue

        success, sig = await execute_buy(mint)
        if success:
            BOUGHT_TOKENS.add(mint)
            with open(BOUGHT_TOKENS_FILE, "w") as f:
                json.dump(list(BOUGHT_TOKENS), f)
            await send_telegram_message(f"✅ Bought {mint}\nTx: {sig}")

        await asyncio.sleep(1)

# [main_loop stays unchanged, as well as the rest of the script]
