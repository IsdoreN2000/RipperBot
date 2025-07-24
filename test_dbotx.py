import os
import aiohttp
import asyncio
from dotenv import load_dotenv

load_dotenv()

DBOTX_API_KEY = os.getenv("DBOTX_API_KEY")
REST_URL = "https://api-data-v1.dbotx.com/kline/new?chain=solana&sortBy=createdAt&sort=desc&interval=1m"
WS_URL = "wss://api-bot-v1.dbotx.com/trade/ws/"

async def test_rest():
    headers = {
        "Authorization": f"Bearer {DBOTX_API_KEY}"
    }
    async with aiohttp.ClientSession(headers=headers) as session:
        async with session.get(REST_URL) as resp:
            print(f"[REST] Status: {resp.status}")
            data = await resp.text()
            print(f"[REST] Response:\n{data}")

async def test_ws():
    headers = {
        "Authorization": f"Bearer {DBOTX_API_KEY}"
    }
    async with aiohttp.ClientSession() as session:
        try:
            async with session.ws_connect(WS_URL, headers=headers) as ws:
                print("[WS] WebSocket connected successfully.")
                await ws.send_str("ping")
                msg = await ws.receive(timeout=5)
                print(f"[WS] Received: {msg.data}")
        except Exception as e:
            print(f"[WS] Error: {e}")

async def main():
    if not DBOTX_API_KEY:
        print("❌ API key is missing. Please set DBOTX_API_KEY in .env.")
        return

    print(f"✅ Loaded API Key: {DBOTX_API_KEY[:6]}... (length: {len(DBOTX_API_KEY)})")
    await test_rest()
    await test_ws()

if __name__ == "__main__":
    asyncio.run(main())
