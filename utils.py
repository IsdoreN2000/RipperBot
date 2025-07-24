import os
import aiohttp
import asyncio
import logging
import time
from dotenv import load_dotenv
from filelock import FileLock
from decimal import Decimal
import json
import websockets

load_dotenv()

DBOTX_API_KEY = os.getenv("DBOTX_API_KEY")
TELEGRAM_ENABLED = os.getenv("TELEGRAM_ENABLED") == "true"
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

HEADERS = {"Authorization": f"Bearer {DBOTX_API_KEY}"}

MIN_AGE = 0
MAX_AGE = 360
MIN_LIQUIDITY_SOL = 20
MIN_HOLDERS = 10
MAX_TOP_HOLDER_PERCENT = 30
MIN_MC = 1000
MIN_VOLUME = 1000

POSITIONS_FILE = "positions.json"

logger = logging.getLogger("utils")

JUPITER_SWAP_API = "https://quote-api.jup.ag/v6/swap"

async def send_telegram_message(message: str):
    if not TELEGRAM_ENABLED:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": message}) as resp:
                await resp.text()
        except Exception as e:
            logger.warning(f"[telegram] Failed to send: {e}")

async def get_json(session, url):
    try:
        async with session.get(url, headers=HEADERS) as response:
            if response.status != 200:
                text = await response.text()
                logger.error(f"[get_json] HTTP {response.status}: {text} (URL: {url})")
                return None
            return await response.json()
    except Exception as e:
        logger.error(f"[get_json] Exception: {e}")
        return None

async def get_recent_tokens_from_dbotx(session):
    url = "https://api-data-v1.dbotx.com/kline/new?chain=solana&sortBy=createdAt&sort=desc&interval=1m"
    data = await get_json(session, url)
    if not data or "data" not in data:
        return []

    valid = []
    now = time.time()
    for token in data["data"]:
        created_at = token.get("createdAt", 0) / 1000
        age = now - created_at
        liquidity = float(token.get("liquidity", 0)) / 1e9
        holders = int(token.get("holders", 0))
        top_10 = float(token.get("top10HolderRate", 100))
        mc = float(token.get("marketCapUsd", 0))
        vol = float(token.get("volumeUsd24h", 0))

        if not (MIN_AGE <= age <= MAX_AGE):
            continue
        if liquidity < MIN_LIQUIDITY_SOL:
            continue
        if holders < MIN_HOLDERS:
            continue
        if top_10 > MAX_TOP_HOLDER_PERCENT:
            continue
        if mc < MIN_MC:
            continue
        if vol < MIN_VOLUME:
            continue

        valid.append(token)
    return valid

async def simulate_buy(session, token):
    url = "https://api-bot-v1.dbotx.com/simulator/snipe_order"
    body = {
        "chain": "solana",
        "tokenAddress": token["tokenAddress"],
        "amountUsd": 5
    }
    try:
        async with session.post(url, json=body, headers=HEADERS) as resp:
            result = await resp.json()
            if resp.status == 200 and result.get("success"):
                logger.info(f"[buy] Success: {token['name']}")
                await send_telegram_message(f"✅ Bought {token['name']} | {token['tokenAddress']}")
                await save_position(token)
            else:
                logger.warning(f"[buy] Failed: {result}")
    except Exception as e:
        logger.error(f"[buy] Exception: {e}")

async def save_position(token):
    lock = FileLock(f"{POSITIONS_FILE}.lock")
    with lock:
        if os.path.exists(POSITIONS_FILE):
            with open(POSITIONS_FILE, "r") as f:
                data = json.load(f)
        else:
            data = {}
        data[token['tokenAddress']] = {
            "name": token['name'],
            "symbol": token['symbol'],
            "price": token.get("priceUsd", 0),
            "bought_at": time.time(),
            "tokenAddress": token['tokenAddress']
        }
        with open(POSITIONS_FILE, "w") as f:
            json.dump(data, f, indent=2)

async def listen_to_dbotx_trades():
    url = "wss://api-bot-v1.dbotx.com/trade/ws/"
    headers = [("Authorization", f"Bearer {DBOTX_API_KEY}")]
    try:
        async with websockets.connect(url, extra_headers=headers) as ws:
            logger.info("[ws] Connected to DBotX WebSocket.")
            async for msg in ws:
                logger.info(f"[ws] Message: {msg}")
    except Exception as e:
        logger.error(f"[ws] Connection error: {e}")

# ✅ Add missing function
async def has_sufficient_liquidity(mint, min_liquidity_lamports):
    """
    Check if the token has sufficient output liquidity via Jupiter.
    Uses 0.01 SOL (10_000_000 lamports) to simulate a swap.
    """
    url = f"{JUPITER_SWAP_API}?inputMint=So11111111111111111111111111111111111111112&outputMint={mint}&amount=10000000"

    async with aiohttp.ClientSession() as session:
        data = await get_json(session, url)
        if not data or "data" not in data:
            return False

        routes = data.get("data", [])
        if not routes:
            return False

        # Check best route's output value
        best_route = routes[0]
        out_amount = int(best_route.get("outAmount", 0))
        return out_amount >= min_liquidity_lamports
