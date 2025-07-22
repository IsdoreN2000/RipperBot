import asyncio
import aiohttp
import json
import logging
import os
from typing import List, Dict, Optional
from collections import deque

# === Configuration ===
DBOTX_WS_URL = "wss://api-bot-v1.dbotx.com/trade/ws"
DBOTX_API_KEY = os.getenv("DBOTX_API_KEY") or "YOUR_TEST_API_KEY"
MAX_TOKENS = 100

JUPITER_BASE_URL = "https://quote-api.jup.ag"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

detected_tokens = deque(maxlen=MAX_TOKENS)

# --- DBotX WebSocket Listener ---
async def listen_to_dbotx_trades(chain: str = "solana"):
    headers = {"X-API-KEY": DBOTX_API_KEY}
    backoff = 1
    while True:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.ws_connect(DBOTX_WS_URL, headers=headers) as ws:
                    logger.info(f"[ws] Connected to DBotX WebSocket (chain={chain})")
                    subscribe_msg = {
                        "event": "subscribe",
                        "channel": "trades",
                        "chain": chain
                    }
                    await ws.send_json(subscribe_msg)
                    backoff = 1
                    async for msg in ws:
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            try:
                                data = json.loads(msg.data)
                                logger.debug(f"[ws] Received: {data}")
                                if "token" in data:
                                    token_info = {
                                        "mint": data["token"],
                                        "symbol": data.get("symbol", ""),
                                        "amount": data.get("amount", 0),
                                        "price": data.get("price", 0),
                                        "timestamp": data.get("timestamp") or int(asyncio.get_event_loop().time())
                                    }
                                    detected_tokens.append(token_info)
                                    logger.info(f"[ws] New token detected: {token_info}")
                            except json.JSONDecodeError:
                                logger.warning(f"[ws] Invalid JSON: {msg.data}")
                        elif msg.type == aiohttp.WSMsgType.ERROR:
                            logger.error("[ws] WebSocket error: %s", msg.data)
                            break
        except asyncio.CancelledError:
            logger.info("[ws] Listener cancelled, shutting down gracefully.")
            break
        except Exception as e:
            logger.error(f"[ws] Connection error: {e}")
            logger.info(f"[ws] Reconnecting in {backoff} seconds...")
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 60)

def get_recent_tokens_from_dbotx(limit: int = 20) -> List[Dict]:
    return list(detected_tokens)[-limit:] if detected_tokens else []

# --- Utility: Retry logic for network requests ---
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

# --- Liquidity check ---
async def has_sufficient_liquidity(mint, min_liquidity_lamports):
    url = f"{JUPITER_BASE_URL}/v6/pools?mint={mint}"
    async with aiohttp.ClientSession() as session:
        data = await fetch_with_retries(session, url)
        if not data:
            return False
        for pool in data.get("pools", []):
            if int(pool.get("lp_fee_bps", 0)) > 100:
                continue
            base_liq = int(pool.get("base_liquidity", 0))
            quote_liq = int(pool.get("quote_liquidity", 0))
            if base_liq >= min_liquidity_lamports or quote_liq >= min_liquidity_lamports:
                return True
    return False

# --- Token metadata ---
async def get_token_metadata(mint):
    url = f"https://token.jup.ag/strict/{mint}"
    async with aiohttp.ClientSession() as session:
        data = await fetch_with_retries(session, url)
        if data:
            return data
    return {"symbol": "Unknown"}

# --- Buy (stub) ---
async def buy_token(mint, amount_sol):
    try:
        logger.info(f"[stub] Simulating buy of {amount_sol} SOL for {mint}")
        return {"success": True, "txid": "dummy_txid"}
    except Exception as e:
        logger.warning(f"[buy] failed: {e}")
        return {"success": False, "error": str(e)}

# --- Sell (stub) ---
async def sell_token(mint, amount_token=None):
    try:
        logger.info(f"[stub] Simulating sell of {mint}")
        return {"success": True, "txid": "dummy_txid"}
    except Exception as e:
        logger.warning(f"[sell] failed: {e}")
        return {"success": False, "error": str(e)}

# --- Get token price ---
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

# --- Telegram notification (stub) ---
async def send_telegram_message(message: str):
    logger.info(f"[telegram] {message}")

# --- END OF UTILS.PY ---
