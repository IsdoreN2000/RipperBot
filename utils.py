import aiohttp
import asyncio
import logging
import os
import json
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("utils")

DBOTX_API_KEY = os.getenv("DBOTX_API_KEY")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

if not DBOTX_API_KEY:
    raise RuntimeError("Missing DBOTX_API_KEY in .env")

DBOTX_BASE_URL = "https://api-data-v1.dbotx.com"
DBOTX_TRADE_URL = "https://api-bot-v1.dbotx.com"
DBOTX_WS_URL = "wss://api-bot-v1.dbotx.com/trade/ws/"

HEADERS = {
    "x-api-key": DBOTX_API_KEY
}


async def get_json(session, url):
    try:
        async with session.get(url, headers=HEADERS) as resp:
            if resp.status == 200:
                return await resp.json()
            else:
                logger.error(f"[get_json] HTTP {resp.status}: {await resp.text()} (URL: {url})")
                return {}
    except Exception as e:
        logger.error(f"[get_json] Error fetching {url}: {e}")
        return {}


async def get_recent_tokens_from_dbotx(session):
    url = f"{DBOTX_BASE_URL}/kline/new?chain=solana&sortBy=createdAt&sort=desc&interval=1m"
    data = await get_json(session, url)
    tokens = []
    if data and "data" in data:
        for token in data["data"]:
            tokens.append({
                "mint": token["tokenAddress"],
                "timestamp": token["createdAt"]
            })
    return tokens


async def has_sufficient_liquidity(mint, min_liquidity_lamports):
    url = f"https://quote-api.jup.ag/v6/pools?inputMint={mint}&outputMint=So11111111111111111111111111111111111111112"
    async with aiohttp.ClientSession() as session:
        data = await get_json(session, url)
        if not data:
            return False
        for pool in data.get("pools", []):
            if pool.get("liquidity", 0) >= min_liquidity_lamports:
                return True
        return False


async def get_token_metadata(token_address: str) -> dict:
    url = f"{DBOTX_BASE_URL}/token/metadata?chain=solana&tokenAddress={token_address}"
    async with aiohttp.ClientSession(headers=HEADERS) as session:
        async with session.get(url) as resp:
            if resp.status == 200:
                data = await resp.json()
                return data.get("data", {})
            else:
                logger.warning(f"[meta] Failed to fetch metadata for {token_address}: {resp.status}")
                return {}


async def buy_token(mint, amount_sol):
    logger.info(f"[buy] Buying {mint} for {amount_sol} SOL (stubbed)")
    await asyncio.sleep(1)
    return {"success": True}


async def sell_token(mint):
    logger.info(f"[sell] Selling {mint} (stubbed)")
    await asyncio.sleep(1)
    return {"success": True}


async def get_token_price(mint):
    url = f"https://price.jup.ag/v4/price?ids={mint}"
    async with aiohttp.ClientSession() as session:
        data = await get_json(session, url)
        if not data or "data" not in data or mint not in data["data"]:
            return 0
        return data["data"][mint]["price"]


async def send_telegram_message(msg):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        logger.warning("[telegram] Missing credentials")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": msg
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload) as resp:
                if resp.status != 200:
                    logger.warning(f"[telegram] Failed: {resp.status} {await resp.text()}")
    except Exception as e:
        logger.warning(f"[telegram] Error: {e}")


async def listen_to_dbotx_trades():
    try:
        async with aiohttp.ClientSession(headers=HEADERS) as session:
            async with session.ws_connect(DBOTX_WS_URL, headers=HEADERS) as ws:
                logger.info("[ws] Connected to DBotX trade websocket")
                async for msg in ws:
                    if msg.type == aiohttp.WSMsgType.TEXT:
                        logger.debug(f"[ws] Message: {msg.data}")
                    elif msg.type == aiohttp.WSMsgType.ERROR:
                        logger.error(f"[ws] Error: {msg.data}")
    except Exception as e:
        logger.error(f"[ws] Connection error: {e}")
        await asyncio.sleep(5)
        await listen_to_dbotx_trades()
