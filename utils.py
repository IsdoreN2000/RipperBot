import aiohttp
import asyncio
import base64
import json
import logging
import os
import time
from decimal import Decimal

# --- Dependency Check: solana and solders ---
try:
    from solana.publickey import PublicKey
except Exception as e:
    print(f"[startup][error] Failed to import solana.publickey: {e}")
    raise

try:
    from solders.pubkey import Pubkey
except Exception as e:
    print(f"[startup][error] Failed to import solders.pubkey: {e}")
    raise

from filelock import FileLock
from dotenv import load_dotenv

load_dotenv()

HELIUS_API_KEY = os.getenv("HELIUS_API_KEY")
HELIUS_BASE_URL = f"https://mainnet.helius-rpc.com/?api-key={HELIUS_API_KEY}"
JUPITER_API_BASE_URL = "https://quote-api.jup.ag"

HEADERS = {
    "accept": "application/json",
    "Content-Type": "application/json"
}

logger = logging.getLogger(__name__)

# --- Fetch recent tokens from Helius ---
async def get_recent_tokens_from_helius(program_ids):
    url = f"{HELIUS_BASE_URL}"
    limit = 20
    seen_mints = set()
    recent_tokens = []

    async with aiohttp.ClientSession() as session:
        for program_id in program_ids:
            payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "getSignaturesForAddress",
                "params": [program_id, {"limit": limit}]
            }
            async with session.post(url, json=payload, headers=HEADERS) as resp:
                result = await resp.json()
                signatures = result.get("result", [])

                for sig in signatures:
                    signature = sig["signature"]
                    ts = sig.get("blockTime", int(time.time()))
                    token_info = await fetch_token_mint_from_signature(session, signature)
                    if token_info:
                        mint = token_info["mint"]
                        if mint not in seen_mints:
                            seen_mints.add(mint)
                            recent_tokens.append({
                                "mint": mint,
                                "timestamp": ts
                            })
    return recent_tokens

# --- Helper: fetch token mint from a transaction signature ---
async def fetch_token_mint_from_signature(session, signature):
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "getTransaction",
        "params": [signature, {"encoding": "json"}]
    }
    async with session.post(HELIUS_BASE_URL, json=payload, headers=HEADERS) as resp:
        result = await resp.json()
        transaction = result.get("result")
        if not transaction:
            return None
        try:
            instructions = transaction["transaction"]["message"]["instructions"]
            for ix in instructions:
                if "parsed" in ix:
                    parsed = ix["parsed"]
                    if parsed["type"] == "initializeMint":
                        return {"mint": parsed["info"]["mint"]}
        except Exception:
            return None
    return None

# --- Check if a token has sufficient liquidity ---
async def has_sufficient_liquidity(mint: str, min_liquidity_lamports: int) -> bool:
    url = f"{JUPITER_API_BASE_URL}/v6/pools?mint={mint}"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            data = await resp.json()
            for pool in data:
                reserves = pool.get("reserves", [])
                for reserve in reserves:
                    if reserve and int(reserve) >= min_liquidity_lamports:
                        return True
    return False

# --- Fetch token metadata (placeholder) ---
async def get_token_metadata(mint):
    return {"name": mint[:4]}  # Placeholder for real metadata fetch

# --- Buy token (mock implementation) ---
async def buy_token(mint, amount_sol, tip=5000):
    return {"success": True}  # Mock response

# --- Get token price (mock implementation) ---
async def get_token_price(mint):
    return 1.0  # Mock price

# --- Sell token (mock implementation) ---
async def sell_token(mint):
    logger.info(f"[mock sell] Selling token {mint}")

# --- Send Telegram message (mock implementation) ---
async def send_telegram_message(message: str):
    logger.info(f"[telegram] {message}")

# --- Async load positions from file ---
async def load_positions(filepath: str):
    try:
        loop = asyncio.get_event_loop()
        if not os.path.exists(filepath):
            return {}
        return await loop.run_in_executor(None, lambda: json.load(open(filepath, "r")))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

# --- Async save positions to file with file lock ---
async def save_positions(filepath: str, positions: dict, lockfile: str):
    loop = asyncio.get_event_loop()
    def write_json():
        with FileLock(lockfile):
            with open(filepath, "w") as f:
                json.dump(positions, f, indent=4)
    await loop.run_in_executor(None, write_json)

# --- Acquire file lock (sync, for startup/shutdown) ---
async def acquire_file_lock(lockfile: str):
    loop = asyncio.get_event_loop()
    def acquire():
        lock = FileLock(lockfile)
        lock.acquire()
    await loop.run_in_executor(None, acquire)

# --- Release file lock (sync, for shutdown) ---
async def release_file_lock(lockfile: str):
    loop = asyncio.get_event_loop()
    def release():
        lock = FileLock(lockfile)
        if lock.is_locked:
            lock.release()
    await loop.run_in_executor(None, release)
