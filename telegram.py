import os
import aiohttp
import asyncio

from utils import send_telegram_message

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

async def handle_command():
    last_update_id = None
    while True:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates"
        if last_update_id:
            url += f"?offset={last_update_id + 1}"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as resp:
                    data = await resp.json()
                    for update in data.get("result", []):
                        last_update_id = update["update_id"]
                        message = update.get("message", {}).get("text", "")
                        if not message:
                            continue
                        if message == "/latest":
                            await send_telegram_message("🕵️‍♂️ No active tokens stored in memory yet.")
                        else:
                            await send_telegram_message("❓ Unknown command. Try /latest")
        except Exception as e:
            print("Telegram polling error:", e)
        await asyncio.sleep(5)

