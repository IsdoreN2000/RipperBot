import os
import aiohttp
import logging
import time
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
    try:
        headers = {"Content-Type": "application/json"}
        now = int(time.time())
        for program_id in program_ids:
            url = f"https://mainnet.helius.xyz/v0/addresses/{program_id}/transactions?api-key={HELIUS_API_KEY}&limit={limit}"
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers) as resp:
                    if resp.status != 200:
                        logger.warning(f"Helius API status: {resp.status}")
                        raw = await resp.text()
                        logger.warning(f"Helius API raw response: {raw}")
                        continue
                    data = await resp.json()
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
    except Exception as e:
        logger.warning(f"Helius token fetch failed: {e}")
    return tokens

# === Liquidity check ===

async def has_sufficient_liquidity(mint, min_liquidity_lamports):
    try:
        url = f"{JUPITER_BASE_URL}/v6/pools?mint={mint}"
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status != 200:
                    logger.warning(f"[liquidity] HTTP {resp.status}")
                    return False
                data = await resp.json()
                for pool in data.get("pools", []):
                    if int(pool.get("lp_fee_bps", 0)) > 100:  # filter scammy pools
                        continue
                    base_liq = int(pool.get("base_liquidity", 0))
                    quote_liq = int(pool.get("quote_liquidity", 0))
                    if base_liq >= min_liquidity_lamports or quote_liq >= min_liquidity_lamports:
                        return True
    except Exception as e:
        logger.warning(f"[liquidity] check failed: {e}")
    return False

# === Token metadata ===

async def get_token_metadata(mint):
    try:
        url = f"https://token.jup.ag/strict/{mint}"
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status == 200:
                    return await resp.json()
    except Exception as e:
        logger.warning(f"[metadata] fetch failed: {e}")
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
    try:
        url = f"https://price.jup.ag/v4/price?ids={mint}"
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                data = await resp.json()
        price_data = data.get("data", {}).get(mint)
        if price_data:
            return price_data["price"]
        else:
            logger.warning(f"[price] No price for {mint}")
            return None
    except Exception as e:
        logger.warning(f"[price] fetch error: {e}")
        return None
