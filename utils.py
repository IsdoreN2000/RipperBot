import aiohttp
import asyncio
import logging
import os
import time
from decimal import Decimal
from typing import Any, Dict, List, Optional

# --- Constants ---
DBOTX_DATA_API = "https://api-data-v1.dbotx.com"
DBOTX_SIMULATOR_API = "https://api-bot-v1.dbotx.com/simulator/snipe_order"
JUP_QUOTE_API = "https://quote-api.jup.ag/v6/quote"
DEXSCREENER_API = "https://api.dexscreener.com/latest/dex/pairs/solana"
JUP_PRICE_API = "https://price.jup.ag/v4/price"

MIN_HOLDERS = 10
MAX_TOP10_PERCENT = 30
MIN_MARKET_CAP = 1000
MIN_VOLUME = 1000
MIN_TOKEN_AGE_SECONDS = 0
MAX_TOKEN_AGE_SECONDS = 360
MAX_PRICE_IMPACT = 0.5

logger = logging.getLogger(__name__)

# --- Helper Functions ---

async def get_json(session: aiohttp.ClientSession, url: str) -> Optional[Dict[str, Any]]:
    try:
        async with session.get(url) as resp:
            if resp.status != 200:
                logger.error(f"[get_json] HTTP {resp.status}: {await resp.text()} (URL: {url})")
                return None
            return await resp.json()
    except aiohttp.ClientError as e:
        logger.error(f"[get_json] Client error fetching {url}: {e}")
    except Exception as e:
        logger.error(f"[get_json] Unexpected error fetching {url}: {e}")
    return None

# --- Main Logic Functions ---

async def get_recent_tokens_from_dbotx(session: aiohttp.ClientSession) -> List[Dict[str, Any]]:
    url = f"{DBOTX_DATA_API}/kline/new?chain=solana&sortBy=createdAt&sort=desc&interval=1m"
    data = await get_json(session, url)
    if not data or "data" not in data:
        return []

    tokens = []
    for item in data["data"]:
        try:
            mint = item.get("baseMint")
            if not mint:
                continue

            created_at = item.get("createdAt")
            if not created_at:
                continue
            timestamp = created_at / 1000
            age = time.time() - timestamp
            # --- Updated age filter ---
            if not (MIN_TOKEN_AGE_SECONDS <= age <= MAX_TOKEN_AGE_SECONDS):
                continue

            token_info = await get_token_info(session, mint)
            if not token_info:
                continue

            if (
                token_info["holder_count"] < MIN_HOLDERS or
                token_info["top_holders_percent"] > MAX_TOP10_PERCENT or
                token_info["market_cap"] < MIN_MARKET_CAP or
                token_info["volume_24h"] < MIN_VOLUME
            ):
                continue

            tokens.append({
                "mint": mint,
                "timestamp": timestamp,
                "symbol": token_info["symbol"],
                "name": token_info["name"]
            })
        except Exception as e:
            logger.warning(f"[parse token] Error: {e} (item: {item})")
            continue

    return tokens

async def get_token_info(session: aiohttp.ClientSession, mint: str) -> Optional[Dict[str, Any]]:
    url = f"{DBOTX_DATA_API}/token/info?chain=solana&address={mint}"
    data = await get_json(session, url)
    if not data or "data" not in data:
        return None
    info = data["data"]
    return {
        "holder_count": info.get("holders", 0),
        "top_holders_percent": info.get("top10HoldersPercent", 100),
        "market_cap": info.get("marketCap", 0),
        "volume_24h": info.get("volume24h", 0),
        "symbol": info.get("symbol", ""),
        "name": info.get("name", "")
    }

async def has_sufficient_liquidity(session: aiohttp.ClientSession, mint: str, min_liquidity: int) -> bool:
    url = f"{JUP_QUOTE_API}?inputMint={mint}&outputMint=So11111111111111111111111111111111111111112&amount=1000000"
    data = await get_json(session, url)
    if not data or "routes" not in data or not data["routes"]:
        return False
    route = data["routes"][0]
    in_amount = int(route.get("inAmount", 0))
    out_amount = int(route.get("outAmount", 0))
    price_impact = float(route.get("priceImpactPct", 1))
    return in_amount > 0 and out_amount > 0 and price_impact < MAX_PRICE_IMPACT

async def get_token_metadata(session: aiohttp.ClientSession, mint: str) -> Dict[str, str]:
    url = f"{DEXSCREENER_API}/{mint}"
    data = await get_json(session, url)
    if not data:
        return {"symbol": "UNKNOWN", "name": ""}
    return {
        "symbol": data.get("pair", {}).get("baseToken", {}).get("symbol", "UNKNOWN"),
        "name": data.get("pair", {}).get("baseToken", {}).get("name", "")
    }

async def get_token_price(session: aiohttp.ClientSession, mint: str) -> Optional[float]:
    url = f"{JUP_PRICE_API}?ids={mint}"
    data = await get_json(session, url)
    if not data:
        return None
    price = data.get("data", {}).get(mint, {}).get("price")
    return float(price) if price else None

async def buy_token(session: aiohttp.ClientSession, mint: str, amount_sol: float) -> Dict[str, Any]:
    payload = {
        "chain": "solana",
        "mint": mint,
        "amount": amount_sol,
        "action": "buy"
    }
    try:
        async with session.post(DBOTX_SIMULATOR_API, json=payload) as resp:
            if resp.status != 200:
                return {"success": False, "error": await resp.text()}
            return {"success": True, "tx": await resp.text()}
    except Exception as e:
        return {"success": False, "error": str(e)}

async def sell_token(session: aiohttp.ClientSession, mint: str) -> bool:
    payload = {
        "chain": "solana",
        "mint": mint,
        "action": "sell"
    }
    try:
        async with session.post(DBOTX_SIMULATOR_API, json=payload) as resp:
            return resp.status == 200
    except Exception as e:
        logger.warning(f"[sell_token] Error: {e}")
        return False

async def send_telegram_message(session: aiohttp.ClientSession, msg: str) -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        logger.warning("[telegram] Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID")
        return
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        async with session.post(url, json={"chat_id": chat_id, "text": msg}) as resp:
            if resp.status != 200:
                logger.warning(f"[telegram] Failed to send message: {await resp.text()}")
    except Exception as e:
        logger.warning(f"[telegram] Exception sending message: {e}")

async def listen_to_dbotx_trades():
    url = "wss://api-bot-v1.dbotx.com/trade/ws/"
    while True:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.ws_connect(url) as ws:
                    logger.info("[ws] Connected to DBotX WebSocket.")
                    async for msg in ws:
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            logger.debug(f"[ws] Message: {msg.data}")
        except Exception as e:
            logger.error(f"[ws] Connection error: {e}")
            await asyncio.sleep(5)

# --- Example Main Entrypoint ---

async def main():
    async with aiohttp.ClientSession() as session:
        tokens = await get_recent_tokens_from_dbotx(session)
        logger.info(f"Found {len(tokens)} recent tokens (age 0-360s).")
        # Example: send a Telegram message for each token
        for token in tokens:
            await send_telegram_message(session, f"New token: {token['symbol']} ({token['mint']})")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
