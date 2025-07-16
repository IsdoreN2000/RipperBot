# ... imports ...
import os
import json
import base64
import aiohttp
import logging
import asyncio
import traceback
from datetime import datetime, timezone

from solders.keypair import Keypair
from solders.transaction import VersionedTransaction
from solana.rpc.async_api import AsyncClient
from solana.rpc.types import TxOpts

logging.basicConfig(level=logging.INFO)
print("=== BOT.PY STARTED ===")

# --- ENVIRONMENT ---
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
STOP_LOSS = float(os.getenv("STOP_LOSS", 0.7))

# --- TRACKER ---
owned_tokens = {}

# --- TELEGRAM ---
async def send_telegram(message):
    if not TELEGRAM_TOKEN or not CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {"chat_id": CHAT_ID, "text": message, "parse_mode": "Markdown"}
    try:
        async with aiohttp.ClientSession() as s:
            await s.post(url, json=data)
    except Exception as e:
        logging.error(f"[Telegram] {e}")

# --- HELIUS SCAN ---
async def get_recent_signatures(limit=10):
    payload = {
        "jsonrpc": "2.0", "id": 1, "method": "getSignaturesForAddress",
        "params": [PUMP_PROGRAM_ID, {"limit": limit}]
    }
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(HELIUS_URL, json=payload, timeout=10) as r:
                return [tx["signature"] for tx in (await r.json()).get("result", [])]
    except Exception as e:
        logging.warning(f"[signatures] {e}")
        return []

async def get_token_mints_from_tx(signature):
    payload = {
        "jsonrpc": "2.0", "id": 1, "method": "getTransaction",
        "params": [signature, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}]
    }
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(HELIUS_URL, json=payload, timeout=10) as r:
                result = await r.json()
                meta = result.get("result", {}).get("meta", {})
                tx = result.get("result", {}).get("transaction", {})
                mints = set()

                for bal in meta.get("preTokenBalances", []) + meta.get("postTokenBalances", []):
                    if "mint" in bal:
                        mints.add(bal["mint"])

                return list(mints)
    except Exception as e:
        logging.warning(f"[mints] {e}")
        return []

async def fetch_recent_tokens(limit=10):
    sigs = await get_recent_signatures(limit)
    mints = set()
    for sig in sigs:
        mints.update(await get_token_mints_from_tx(sig))
    return [{"mint": m} for m in mints if m != WRAPPED_SOL]

# --- JUPITER ---
async def has_liquidity(mint):
    params = {
        "inputMint": WRAPPED_SOL, "outputMint": mint,
        "amount": str(int(BUY_AMOUNT_SOL * 1_000_000_000)),
        "slippageBps": int(SLIPPAGE * 100),
        "onlyDirectRoutes": "true"
    }
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(JUPITER_QUOTE_URL, params=params) as r:
                data = await r.json()
                if r.status != 200 or not data.get("data"):
                    logging.warning(f"[has_liquidity] Error {r.status}: {data}")
                    return False
                return True
    except Exception as e:
        logging.warning(f"[has_liquidity] {e}")
        return False

async def get_swap_route(input_mint, output_mint, amount):
    params = {
        "inputMint": input_mint, "outputMint": output_mint,
        "amount": str(amount),
        "slippageBps": int(SLIPPAGE * 100),
        "onlyDirectRoutes": "true"
    }
    async with aiohttp.ClientSession() as s:
        async with s.get(JUPITER_QUOTE_URL, params=params) as r:
            data = await r.json()
            return data["data"][0] if data.get("data") else None

async def get_swap_tx(route, user_pubkey):
    payload = {
        "route": route, "userPublicKey": user_pubkey,
        "wrapUnwrapSOL": True, "asLegacyTransaction": False
    }
    async with aiohttp.ClientSession() as s:
        async with s.post(JUPITER_SWAP_URL, json=payload) as r:
            data = await r.json()
            return data["swapTransaction"]

async def execute_swap(txn_b64, client):
    txn = VersionedTransaction.deserialize(base64.b64decode(txn_b64))
    txn.sign([keypair])
    sig = await client.send_raw_transaction(txn.serialize(), opts=TxOpts(skip_preflight=True))
    await client.confirm_transaction(sig.value)
    return sig.value

# --- BUY ---
async def execute_buy(mint):
    amount = int(BUY_AMOUNT_SOL * 1_000_000_000)
    async with AsyncClient(RPC_URL) as client:
        route = await get_swap_route(WRAPPED_SOL, mint, amount)
        if not route:
            return False, None
        tx = await get_swap_tx(route, str(keypair.pubkey()))
        sig = await execute_swap(tx, client)
        owned_tokens[mint] = {"bought_at": float(route["outAmount"]) / 10**route["outputMintDecimals"]}
        return True, sig

# --- SELL ---
async def check_and_sell():
    if not owned_tokens:
        return
    for mint, info in list(owned_tokens.items()):
        input_mint = mint
        output_mint = WRAPPED_SOL
        amount = int(info["bought_at"] * 10**6)  # rough estimate
        route = await get_swap_route(input_mint, output_mint, amount)
        if not route:
            continue
        price_now = float(route["outAmount"]) / 10**route["outputMintDecimals"]
        price_in = in_
