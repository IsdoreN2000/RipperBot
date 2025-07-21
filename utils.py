import os
import aiohttp
import logging
import time
import asyncio
from solders.pubkey import Pubkey
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

# === Config ===
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
HELIUS_API_KEY = os.getenv("HELIUS_API_KEY")
JUPITER_BASE_URL = "https://quote-api.jup.ag"

# === Program IDs ===
PUMP_FUN_PROGRAM = "6u6QbZvcj5JkGFsKfJQkRXiRwz9wrDxQ6Uijvqx6uXwp"
BUNK_FUN_PROGRAM = "BUNKU1mDhD6GNnpHJRZAZpEj3nGoqVZZe8RvAdTaLyoz"
PROGRAM_IDS = [PUMP_FUN_PROGRAM, BUNK_FUN_PROGRAM]

# === Helper: Retry logic for network requests ===
async def fetch_with_retries(session, url, headers=None, retries=3, delay=2):
    for attempt in range(retries):
        try:
            async with session.get(url, headers=headers) as resp:
                if resp.status == 200:
                    return await resp.json()
                else:
                    logger.warning(f"HTTP {resp.status} for {url}")
                    raw = await resp.text()
                    logger.warning(f"Raw response: {raw}")
        except Exception as e:
            logger.warning(f"Attempt {attempt+1} failed for {url}: {e}")
        await asyncio.sleep(delay)
    logger.warning(f"All {retries} attempts failed for {url}")
    return None

# === Telegram ===
async def send_telegram_message(message: str):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        logger.warning("Telegram credentials not set")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload) as resp:
                if resp.status != 200:
                    logger.warning(f"[telegram] failed: {resp.status}")
    except Exception as e:
        logger.warning(f"[telegram] error: {e}")

# === Helius token fetch ===
async def get_recent_tokens_from_helius(program_ids=PROGRAM_IDS, limit=10):
    tokens = []
    headers = {"Content-Type": "application/json"}
    now = int(time.time())
    async with aiohttp.ClientSession() as session:
        for program_id in program_ids:
            url = f"https://mainnet.helius.xyz/v0/addresses/{program_id}/transactions?api-key={HELIUS_API_KEY}&limit={limit}"
            data = await fetch_with_retries(session, url, headers)
            if not data:
                continue
            if not isinstance(data, list):
                logger.warning(f"Unexpected data format (expected list): {data}")
                continue
            for tx in data:
                try:
                    mint = None
                    for inst in tx.get("instructions", []):
                        if "mint" in inst and isinstance(inst["mint"], str):
                            mint = inst["mint"]
                            break
                    if not mint:
                        continue
                    tokens.append({
                        "mint": mint,
                        "timestamp": tx.get("timestamp", now)
                    })
                except Exception as e:
                    logger.warning(f"Error parsing transaction: {e}")
    return tokens

# === Liquidity check ===
async def has_sufficient_liquidity(mint, min_liquidity_lamports):
    url = f"{JUPITER_BASE_URL}/v6/pools?mint={mint}"
    async with aiohttp.ClientSession() as session:
        data = await fetch_with_retries(session, url)
        if not data:
            return False
        for pool in data.get("pools", []):
            if int(pool.get("lp_fee_bps", 0)) > 100:  # filter scammy pools
                continue
            base_liq = int(pool.get("base_liquidity", 0))
            quote_liq = int(pool.get("quote_liquidity", 0))
            if base_liq >= min_liquidity_lamports or quote_liq >= min_liquidity_lamports:
                return True
    return False

# === Token metadata ===
async def get_token_metadata(mint):
    url = f"https://token.jup.ag/strict/{mint}"
    async with aiohttp.ClientSession() as session:
        data = await fetch_with_retries(session, url)
        if data:
            return data
    return {"symbol": "Unknown"}

# === Buy ===
async def buy_token(mint, amount_sol):
    try:
        # Replace with actual buy logic
        logger.info(f"[stub] Simulating buy of {amount_sol} SOL for {mint}")
        return {"success": True, "txid": "dummy_txid"}
    except Exception as e:
        logger.warning(f"[buy] failed: {e}")
        return {"success": False, "error": str(e)}

# === Sell ===
async def sell_token(mint, amount_token=None):
    try:
        # Replace with actual sell logic
        logger.info(f"[stub] Simulating sell of {mint}")
        return {"success": True, "txid": "dummy_txid"}
    except Exception as e:
        logger.warning(f"[sell] failed: {e}")
        return {"success": False, "error": str(e)}

# === Get token price ===
async def get_token_price(mint):
    url = f"https://price.jup.ag/v4/price?ids={mint}"
    async with aiohttp.ClientSession() as session:
        data = await fetch_with_retries(session, url)
        if data:
            price_data = data.get("data", {}).get(mint)
            if price_data:
                return price_data["price"]
            else:
                logger.warning(f"[price] No price for {mint}")
    return None
