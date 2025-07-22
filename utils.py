import asyncio
import aiohttp
import json
import logging
import os
import signal
from typing import List, Dict
from collections import deque
from dotenv import load_dotenv

# === Load environment variables early ===
load_dotenv()

# === Configuration ===
DBOTX_WS_URL = "wss://api-bot-v1.dbotx.com/trade/ws"
DBOTX_API_KEY = os.getenv("DBOTX_API_KEY")
if not DBOTX_API_KEY:
    raise ValueError("Missing DBOTX_API_KEY in environment variables.")
MAX_TOKENS = 100

# === Logging Setup ===
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

detected_tokens = deque(maxlen=MAX_TOKENS)

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
                                        "price": data.get("price", 0)
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

async def main():
    listener_task = asyncio.create_task(listen_to_dbotx_trades(chain="solana"))
    try:
        while True:
            await asyncio.sleep(10)
            recent = get_recent_tokens_from_dbotx()
            if recent:
                logger.info(f"Recent tokens: {recent}")
            else:
                logger.info("No tokens detected yet.")
    except KeyboardInterrupt:
        logger.info("Shutting down...")
        listener_task.cancel()
        await listener_task

def shutdown():
    logger.info("Received shutdown signal.")
    raise KeyboardInterrupt

if __name__ == "__main__":
    signal.signal(signal.SIGTERM, lambda s, f: shutdown())
    asyncio.run(main())
