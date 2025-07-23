import os
import time
import json
import logging
import aiohttp
from decimal import Decimal

from dotenv import load_dotenv

load_dotenv()

DBOTX_API_KEY = os.getenv("DBOTX_API_KEY")
JUPITER_SWAP_API = "https://quote-api.jup.ag/v6/quote"
SOL_DECIMALS = 1_000_000_000
MIN_HOLDERS = 10
MAX_TOP_HOLDER_PERCENT = 30
MIN_MARKET_CAP = 1000
MIN_VOLUME = 1000

logger = logging.getLogger("utils")

headers = {
    "Authorization": f"Bearer {DBOTX_API_KEY}"
}

async def get_json(session, url):
    try:
        async with session.get(url, headers=headers) as resp:
            if resp.status == 403:
                body = await resp.text()
                logger.error(f"[get_json] HTTP 403: {body} (URL: {url})")
                return None
            if resp.status != 200:
                logger.warning(f"[get_json] HTTP {resp.status}: {url}")
                return None
            return await resp.json()
    except Exception as e:
        logger.error(f"[get_json] error: {e}")
        return None

async def get_recent_tokens_from_dbotx(session):
    url = "https://api-data-v1.dbotx.com/kline/new?chain=solana&sortBy=createdAt&sort=desc&interval=1m"
    data = await get_json(session, url)
    if not data or not isinstance(data, list):
        return []

    filtered_tokens = []
    now = time.time()

    for token in data:
        mint = token.get("baseMint")
        timestamp = token.get("createdAt")
        liquidity = token.get("liquidity", 0)
        holders = token.get("holders", [])
        market_cap = token.get("marketCap", 0)
        volume = token.get("volume24h", 0)

        if not mint or not timestamp:
            continue

        age = now - (timestamp / 1000)
        if age < 0 or age > 360:
            continue
        if liquidity < 20 * SOL_DECIMALS:
            continue
        if len(holders) < MIN_HOLDERS:
            continue

        total_supply = sum([h.get("balance", 0) for h in holders])
        top_10 = sorted(holders, key=lambda h: h.get("balance", 0), reverse=True)[:10]
        top_10_total = sum([h.get("balance", 0) for h in top_10])
        top_10_percent = (top_10_total / total_supply) * 100 if total_supply else 100

        if top_10_percent > MAX_TOP_HOLDER_PERCENT:
            continue
        if market_cap < MIN_MARKET_CAP:
            continue
        if volume < MIN_VOLUME:
            continue

        filtered_tokens.append({
            "mint": mint,
            "timestamp": timestamp / 1000,
            "symbol": token.get("baseSymbol"),
        })

    return filtered_tokens

async def has_sufficient_liquidity(mint, min_liquidity_lamports):
    url = f"{JUPITER_SWAP_API}?inputMint=So11111111111111111111111111111111111111112&outputMint={mint}&amount=10000000"
    async with aiohttp.ClientSession() as session:
        data = await get_json(session, url)
    if not data:
        return False

    routes = data.get("data", [])
    if not routes:
        return False

    best = routes[0]
    out_amt = int(best.get("outAmount", 0))
    return out_amt > 0

async def get_token_metadata(mint):
    # Simulate token metadata fetch (replace with real logic if needed)
    return {
        "symbol": f"TKN",
        "name": f"Token {mint[:4]}"
    }

async def buy_token(mint, amount_sol):
    # Simulate buy logic
    logger.info(f"[buy_token] Buying {mint} with {amount_sol} SOL")
    return {"success": True, "tx": "mock_tx_id"}

async def get_token_price(mint):
    # Simulate price lookup (replace with real price source)
    return round(Decimal("0.0001") * (time.time() % 100), 6)

async def sell_token(mint):
    # Simulate sell logic
    logger.info(f"[sell_token] Selling {mint}")
    return True

async def send_telegram_message(text):
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not bot_token or not chat_id:
        logger.warning("[telegram] Missing credentials")
        return
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    data = {"chat_id": chat_id, "text": text}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, data=data) as resp:
                if resp.status != 200:
                    logger.warning(f"[telegram] Failed to send: {resp.status}")
    except Exception as e:
        logger.warning(f"[telegram] Error: {e}")

async def listen_to_dbotx_trades():
    import websockets
    import asyncio

    ws_url = "wss://api-bot-v1.dbotx.com/trade/ws/"

    async def listen():
        try:
            async with websockets.connect(ws_url, extra_headers=headers) as ws:
                logger.info("[ws] Connected to DBotX WebSocket.")
                while True:
                    try:
                        msg = await ws.recv()
                        logger.debug(f"[ws] Received: {msg}")
                    except Exception as e:
                        logger.warning(f"[ws] Error: {e}")
                        break
        except Exception as e:
            logger.error(f"[ws] Connection error: {e}")

    while True:
        await listen()
        await asyncio.sleep(5)
