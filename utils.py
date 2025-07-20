import aiohttp
import base64
import json
import logging
import os
import time
from solders.pubkey import Pubkey
from solana.rpc.async_api import AsyncClient
from solana.rpc.types import MemcmpOpts, TokenAccountOpts
from solana.publickey import PublicKey
from filelock import FileLock

MIN_AGE_SECONDS = int(os.getenv("MIN_TOKEN_AGE_SECONDS", 0))
MAX_AGE_SECONDS = int(os.getenv("MAX_TOKEN_AGE_SECONDS", 3600))
HELIUS_URL = os.getenv("HELIUS_URL")
JUPITER_SWAP_URL = "https://quote-api.jup.ag/v6/swap"
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

async def get_recent_tokens_from_helius(program_ids):
    headers = {"Content-Type": "application/json"}
    all_tokens = []

    async with aiohttp.ClientSession() as session:
        for program_id in program_ids:
            url = f"{HELIUS_URL}/v0/addresses/{program_id}/transactions?limit=10"
            try:
                async with session.get(url, headers=headers, timeout=10) as resp:
                    data = await resp.json()
                    for tx in data:
                        token = None
                        for instruction in tx.get("instructions", []):
                            if "mint" in instruction:
                                token = instruction["mint"]
                                break
                        if token:
                            all_tokens.append({"mint": token, "timestamp": tx["timestamp"]})
            except Exception as e:
                logging.warning(f"[helius] error fetching tx from {program_id}: {e}")
    return all_tokens

async def get_token_creation_time(mint, helius_url):
    payload = {
        "jsonrpc": "2.0", "id": 1, "method": "getAccountInfo",
        "params": [mint, {"encoding": "jsonParsed"}]
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(helius_url, json=payload, timeout=10) as resp:
                data = await resp.json()
                block_time = data.get("result", {}).get("value", {}).get("blockTime")
                if block_time:
                    return block_time
    except Exception as e:
        logging.warning(f"[get_token_creation_time] primary failed: {e}")

    payload = {
        "jsonrpc": "2.0", "id": 1, "method": "getSignaturesForAddress",
        "params": [mint, {"limit": 1}]
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(helius_url, json=payload, timeout=10) as resp:
                data = await resp.json()
                sigs = data.get("result", [])
                if sigs:
                    slot = sigs[0].get("slot")
                    if slot:
                        block_time_payload = {
                            "jsonrpc": "2.0", "id": 1, "method": "getBlockTime", "params": [slot]
                        }
                        async with session.post(helius_url, json=block_time_payload, timeout=10) as r:
                            block_data = await r.json()
                            return block_data.get("result")
    except Exception as e:
        logging.warning(f"[get_token_creation_time fallback] {e}")
    return None

async def has_sufficient_liquidity(mint, min_liquidity_lamports):
    try:
        async with aiohttp.ClientSession() as session:
            url = f"https://cache.jup.ag/lite-raydium-pools"
            async with session.get(url, timeout=10) as resp:
                pools = await resp.json()
                for pool in pools:
                    if pool["baseMint"] == mint or pool["quoteMint"] == mint:
                        liquidity = float(pool.get("liquidityUSD", 0)) * 1_000_000_000  # Convert to lamports
                        if liquidity >= min_liquidity_lamports:
                            return True
    except Exception as e:
        logging.warning(f"[liquidity-check] failed: {e}")
    return False

async def get_token_metadata(mint):
    return {"name": f"Token-{mint[:4]}", "symbol": f"TKN", "mint": mint}

async def buy_token(mint, amount_sol, tip=5000):
    try:
        # Simulate success (replace with actual Jupiter call later)
        return {"success": True, "tx": "fake_tx_id"}
    except Exception as e:
        return {"success": False, "error": str(e)}

async def sell_token(mint):
    logging.info(f"[sell] Simulated sell for {mint}")
    return True

async def get_token_price(mint):
    try:
        # Simulate price fetch
        return 0.000123
    except Exception:
        return None

async def send_telegram_message(message):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message}
    try:
        async with aiohttp.ClientSession() as session:
            await session.post(url, data=payload)
    except Exception as e:
        logging.warning(f"[telegram] failed to send message: {e}")

async def load_positions(filename):
    if not os.path.exists(filename):
        return {}
    with open(filename, "r") as f:
        return json.load(f)

async def save_positions(filename, positions, lockfile):
    with FileLock(lockfile):
        with open(filename, "w") as f:
            json.dump(positions, f, indent=2)

async def acquire_file_lock(lockfile):
    FileLock(lockfile).acquire(timeout=10)

async def release_file_lock(lockfile):
    FileLock(lockfile).release()
