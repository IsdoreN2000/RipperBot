import os
import json
import base64
import aiohttp
import logging
import signal
import sys
from datetime import datetime, timezone
from solders.keypair import Keypair
from solders.transaction import VersionedTransaction
from solana.rpc.async_api import AsyncClient
from solana.rpc.types import TxOpts
import asyncio
import traceback

logging.basicConfig(level=logging.INFO)
logging.info("=== Bot started successfully ===")

REQUIRED_ENVS = [
    "PRIVATE_KEY", "HELIUS_API_KEY", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"
]
for var in REQUIRED_ENVS:
    if not os.getenv(var):
        logging.error(f"Missing required environment variable: {var}")
        sys.exit(1)

try:
    PRIVATE_KEY = json.loads(os.getenv("PRIVATE_KEY"))
    keypair = Keypair.from_bytes(bytes(PRIVATE_KEY))
except Exception as e:
    logging.error(f"Invalid PRIVATE_KEY format: {e}")
    sys.exit(1)

HELIUS_API_KEY = os.getenv("HELIUS_API_KEY")
RPC_URL = os.getenv("RPC_URL", f"https://mainnet.helius-rpc.com/?api-key={HELIUS_API_KEY}")
BUY_AMOUNT_SOL = float(os.getenv("BUY_AMOUNT_SOL", 0.01))
SLIPPAGE = float(os.getenv("SLIPPAGE", 3))
PROFIT_TARGET = float(os.getenv("PROFIT_TARGET", 1.5))
STOP_LOSS = float(os.getenv("STOP_LOSS", 0.7))
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
HELIUS_URL = f"https://mainnet.helius-rpc.com/?api-key={HELIUS_API_KEY}"
PUMP_PROGRAM_ID = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
JUPITER_QUOTE_URL = "https://quote-api.jup.ag/v6/quote"
JUPITER_SWAP_URL = "https://quote-api.jup.ag/v6/swap"
WRAPPED_SOL = "So11111111111111111111111111111111111111112"
POSITIONS_FILE = "positions.json"

def load_positions():
    if os.path.exists(POSITIONS_FILE):
        try:
            with open(POSITIONS_FILE, "r") as f:
                return json.load(f)
        except Exception as e:
            logging.warning(f"Failed to load positions: {e}")
    return {}

def save_positions(positions):
    try:
        with open(POSITIONS_FILE, "w") as f:
            json.dump(positions, f)
    except Exception as e:
        logging.warning(f"Failed to save positions: {e}")

positions = load_positions()

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
        for attempt in range(3):
            try:
                async with session.post(url, json=payload, timeout=10) as resp:
                    if resp.status == 429:
                        retry_after = int((await resp.json()).get("parameters", {}).get("retry_after", 1))
                        logging.warning(f"[telegram] Rate limited, retrying in {retry_after}s")
                        await asyncio.sleep(retry_after)
                        continue
                    break
            except Exception as e:
                logging.error(f"[telegram] {e}")
                await asyncio.sleep(2)

async def get_token_creation_time(mint):
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "getSignaturesForAddress",
        "params": [mint, {"limit": 1}]
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(HELIUS_URL, json=payload, timeout=10) as resp:
                result = await resp.json()
                sigs = result.get("result", [])
                if sigs:
                    block_time = sigs[0].get("blockTime")
                    if block_time:
                        return float(block_time)
    except Exception as e:
        logging.warning(f"[creation_time] {e}")
    return None

async def get_recent_signatures(limit=10):
    payload = {
        "jsonrpc": "2.0", "id": 1, "method": "getSignaturesForAddress",
        "params": [PUMP_PROGRAM_ID, {"limit": limit}]
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(HELIUS_URL, json=payload, timeout=10) as resp:
                result = await resp.json()
                return [tx["signature"] for tx in result.get("result", [])]
    except Exception as e:
        logging.warning(f"[signatures] {e}")
        return []

async def get_token_mints_from_tx(signature):
    payload = {
        "jsonrpc": "2.0", "id": 1, "method": "getTransaction",
        "params": [signature, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}]
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(HELIUS_URL, json=payload, timeout=10) as resp:
                result = await resp.json()
                meta = result.get("result", {}).get("meta", {})
                mints = set()
                for bal in meta.get("preTokenBalances", []) + meta.get("postTokenBalances", []):
                    if "mint" in bal:
                        mints.add(bal["mint"])
                return list(mints)
    except Exception as e:
        logging.warning(f"[get_mints] {e}")
        return []

async def fetch_recent_tokens(limit=10):
    signatures = await get_recent_signatures(limit)
    all_mints = set()
    for sig in signatures:
        mints = await get_token_mints_from_tx(sig)
        all_mints.update(mints)
    return [{"mint": mint} for mint in all_mints if mint != WRAPPED_SOL]

async def has_liquidity(mint):
    params = {
        "inputMint": WRAPPED_SOL,
        "outputMint": mint,
        "amount": str(int(BUY_AMOUNT_SOL * 1_000_000_000)),
        "slippageBps": int(SLIPPAGE * 100),
        "onlyDirectRoutes": "false"
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(JUPITER_QUOTE_URL, params=params, timeout=10) as resp:
                data = await resp.json()
                if resp.status != 200:
                    logging.warning(f"[has_liquidity] Error {resp.status}: {data}")
                    return False
                if not data.get("data"):
                    return False
                best_route = data["data"][0]
                out_amount = int(best_route["outAmount"])
                if out_amount < 20 * 1_000_000_000:
                    logging.info(f"[skip] {mint} has only {out_amount / 1_000_000_000:.2f} SOL liquidity")
                    return False
                return True
    except Exception as e
