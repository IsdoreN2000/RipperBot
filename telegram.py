import os
import aiohttp
import asyncio

from utils import send_telegram_message

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

if not TELEGRAM_TOKEN or not CHAT_ID:
    raise EnvironmentError("TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID must be set in environment variables.")

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
                    print("📩 Telegram raw data:", data)  # Debug log

                    for update in data.get("result", []):
                        last_update_id = update["update_id"]

                        message = update.get("message", {})
                        text = message.get("text", "")
                        chat_id = str(message.get("chat", {}).get("id", ""))

                        print("📥 User said:", text)
                        if chat_id != CHAT_ID:
                            print("⚠️ Ignoring message from unknown chat:", chat_id)
                            continue

                        if text == "/start":
                            await send_telegram_message("🤖 Sniper bot is running.")
                        elif text == "/status":
                            await send_telegram_message("✅ Bot is online and scanning.")
                        elif text == "/latest":
                            await send_telegram_message("🕵️‍♂️ No active tokens in memory yet.")
                        else:
                            await send_telegram_message("❌ Unknown command. Try /status or /latest.")
        except Exception as e:
            print("🚨 Telegram polling error:", e)

        await asyncio.sleep(5)
