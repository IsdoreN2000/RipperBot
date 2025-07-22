import os
import aiohttp
import asyncio
import logging
from decimal import Decimal
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

DBOTX_API_KEY = os.getenv("DBOTX_API_KEY")
if not DBOTX_API_KEY:
    raise ValueError("Missing DBOTX_API_KEY in environment variables.")

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# --- Async: Get recent tokens from DBotX ---
async def get_recent_tokens_from_dbotx():
    headers = {
        "X-API-KEY": DBOTX_API_KEY
    }
    url = "https://api-bot-v1.dbotx.com/trade/tokens"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get("tokens", [])
                else:
                    logger.error(f"[get_recent_tokens] HTTP {resp.status}: {await resp.text()}")
    except Exception as e:
        logger.error(f"[get_recent_tokens] error: {e}")
    return []

# --- Token metadata ---
async def get_token_metadata(mint: str):
    # Simulate token metadata lookup (can integrate real metadata fetch later)
    return {
        "symbol": mint[:4].upper(),
        "name": f"Token {mint[:6]}"
    }

# --- Simulated Buy ---
async def buy_token(mint: str, amount_sol: float):
    logger.info(f"[buy] Simulating buy of {amount_sol} SOL for {mint}")
    await asyncio.sleep(1)
    return {"success": True, "tx": "SIMULATED_TX_HASH"}

# --- Simulated Price (pseudo-random for testing) ---
async def get_token_price(mint: str):
    await asyncio.sleep(0.5)
    # Simulate price as random multiple between 0.4x to 2.5x
    import random
    return float(round(random.uniform(0.4, 2.5), 4))

# --- Simulated Sell ---
async def sell_token(mint: str):
    logger.info(f"[sell] Simulating sell for {mint}")
    await asyncio.sleep(1)
    return True

# --- Telegram notification ---
async def send_telegram_message(message: str):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.warning("[telegram] Missing credentials.")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload) as resp:
                if resp.status != 200:
                    logger.warning(f"[telegram] Failed to send message: {await resp.text()}")
    except Exception as e:
        logger.error(f"[telegram] Error sending message: {e}")

# --- Listen to DBotX trades (WebSocket) ---
async def listen_to_dbotx_trades():
    url = "wss://api-bot-v1.dbotx.com/trade/ws"
    headers = {"X-API-KEY": DBOTX_API_KEY}
    while True:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.ws_connect(url, headers=headers) as ws:
                    logger.info("[ws] Connected to DBotX WebSocket.")
                    async for msg in ws:
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            logger.info(f"[ws] Message: {msg.data}")
        except Exception as e:
            logger.error(f"[ws] Connection error: {e}")
            await asyncio.sleep(3)

# --- Placeholder liquidity checker ---
async def has_sufficient_liquidity(token_address: str, min_liquidity_lamports: int) -> bool:
    # DBotX filters already; always return True here
    return True
