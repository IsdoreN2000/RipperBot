import os
import aiohttp
import asyncio
from solders.pubkey import Pubkey

from utils import send_telegram_message, keypair, client

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

auto_score_enabled = True  # Default: ON
last_token_info = {}  # For /watch

async def handle_command():
    global auto_score_enabled
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

                        message = update.get("message", {})
                        text = message.get("text", "")
                        chat_id = str(message.get("chat", {}).get("id", ""))

                        if chat_id != CHAT_ID:
                            continue

                        if not text.startswith("/"):
                            continue  # Ignore non-command messages

                        if text == "/start":
                            await send_telegram_message("🤖 Sniper bot is running.")
                        elif text == "/status":
                            await send_telegram_message("✅ Bot is online and scanning.")
                        elif text == "/latest":
                            await send_telegram_message("🕵️‍♂️ No active tokens in memory yet.")
                        elif text == "/wallet":
                            await show_wallet_balance()
                        elif text == "/watch":
                            await show_watched_token()
                        elif text == "/scoremode on":
                            auto_score_enabled = True
                            await send_telegram_message("✅ AI token scoring enabled.")
                        elif text == "/scoremode off":
                            auto_score_enabled = False
                            await send_telegram_message("⚠️ AI token scoring disabled.")
                        else:
                            await send_telegram_message("❌ Unknown command. Try /wallet, /watch, /scoremode on")
        except Exception as e:
            print("Telegram error:", e)
        await asyncio.sleep(5)


async def show_wallet_balance():
    try:
        sol_balance_resp = await client.get_balance(keypair.pubkey())
        sol = sol_balance_resp.value / 1_000_000_000
        await send_telegram_message(f"💰 Wallet: {sol:.4f} SOL\n🔑 {keypair.pubkey()}")
    except Exception as e:
        await send_telegram_message(f"❌ Failed to fetch balance: {e}")


async def show_watched_token():
    if not last_token_info:
        await send_telegram_message("🔍 No token is being watched right now.")
    else:
        info = last_token_info
        msg = (
            f"👀 Watching token:\n"
            f"• Name: {info.get('name')}\n"
            f"• Mint: {info.get('mint')}\n"
            f"• Age: {info.get('age')}s\n"
            f"• Liquidity: {info.get('liquidity')} SOL\n"
            f"• Holders: {info.get('holders')}\n"
        )
        await send_telegram_message(msg)





