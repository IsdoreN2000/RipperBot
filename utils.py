import os
import aiohttp
import asyncio
import logging
from decimal import Decimal
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

DBOTX_API_KEY = os.getenv("DBOTX_API_KEY")
JUPITER_SWAP_URL = "https://quote-api.jup.ag/v6/swap"
SOL_MINT = "So11111111111111111111111111111111111111112"
USER_WALLET = os.getenv("USER_WALLET")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# --- Async: Get recent tokens from DBotX ---
async def get_recent_tokens_from_dbotx():
    url = "https://api-data-v1.dbotx.com/kline/new?chain=solana&sortBy=createdAt&sort=desc&interval=1m"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get("data", [])
                else:
                    logger.error(f"[get_recent_tokens] HTTP {resp.status}: {await resp.text()}")
    except Exception as e:
        logger.error(f"[get_recent_tokens] error: {e}")
    return []

# --- Token metadata ---
async def get_token_metadata(mint: str):
    return {"symbol": mint[:4].upper()}

# --- Buy token ---
async def buy_token(mint: str, amount_sol: float):
    async with aiohttp.ClientSession() as session:
        payload = {
            "userPublicKey": USER_WALLET,
            "swapMode": "ExactIn",
            "inputMint": SOL_MINT,
            "outputMint": mint,
            "amount": str(int(amount_sol * 1_000_000_000)),
            "slippageBps": 500
        }
        try:
            async with session.post(JUPITER_SWAP_URL, json=payload) as resp:
                if resp.status == 200:
                    result = await resp.json()
                    logger.info(f"[buy_token] Quote: {result.get('outAmount')} for {mint}")
                    return {"success": True, "tx": result.get("swapTransaction")}
                else:
                    logger.warning(f"[buy_token] HTTP {resp.status}: {await resp.text()}")
        except Exception as e:
            logger.error(f"[buy_token] error: {e}")
    return {"success": False, "error": "Buy failed"}

# --- Sell token ---
async def sell_token(mint: str):
    async with aiohttp.ClientSession() as session:
        payload = {
            "userPublicKey": USER_WALLET,
            "swapMode": "ExactIn",
            "inputMint": mint,
            "outputMint": SOL_MINT,
            "amount": "100000",  # This should ideally reflect your real balance
            "slippageBps": 500
        }
        try:
            async with session.post(JUPITER_SWAP_URL, json=payload) as resp:
                if resp.status == 200:
                    result = await resp.json()
                    logger.info(f"[sell_token] Quote: {result.get('outAmount')} SOL")
                    return True
                else:
                    logger.warning(f"[sell_token] HTTP {resp.status}: {await resp.text()}")
        except Exception as e:
            logger.error(f"[sell_token] error: {e}")
    return False

# --- Token price (stub for demo) ---
async def get_token_price(mint: str):
    return float(1.0)

# --- Telegram notification ---
async def send_telegram_message(message: str):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.warning("[telegram] Missing credentials.")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload) as resp:
                if resp.status != 200:
                    logger.warning(f"[telegram] Failed to send: {await resp.text()}")
    except Exception as e:
        logger.error(f"[telegram] Error: {e}")

# --- WebSocket Listener ---
async def listen_to_dbotx_trades():
    url = "wss://api-data-v1.dbotx.com/data/ws/"
    while True:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.ws_connect(url) as ws:
                    logger.info("[ws] Connected to DBotX WebSocket.")
                    async for msg in ws:
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            logger.info(f"[ws] Message: {msg.data}")
        except Exception as e:
            logger.error(f"[ws] Connection error: {e}")
            await asyncio.sleep(1)

# --- Sufficient Liquidity Check (placeholder) ---
async def has_sufficient_liquidity(mint: str, min_liquidity: int) -> bool:
    return True
