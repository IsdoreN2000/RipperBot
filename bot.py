import os
import time
import requests
import json
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
from telegram import Bot

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
PHANTOM_PRIVATE_KEY = os.getenv("PHANTOM_PRIVATE_KEY")
MAIN_WITHDRAW_WALLET = os.getenv("MAIN_WITHDRAW_WALLET")

if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
    raise ValueError("Missing Telegram credentials in environment variables.")

bot = Bot(token=TELEGRAM_TOKEN)

def send_telegram_alert(message):
    try:
        bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
    except Exception as e:
        print(f"[Telegram Error] {e}")

def scan_new_tokens():
    try:
        response = requests.get("https://pump.fun/api/tokens", timeout=10)
        tokens = response.json()
        if isinstance(tokens, list):
            return tokens[:1]
        else:
            print("[API Error] Unexpected response format.")
            return []
    except requests.RequestException as e:
        print(f"[API Error] {e}")
        return []

def auto_buy(token_info):
    token_name = token_info.get("name", "Unknown")
    message = f"[BUY] Token: {token_name}\nDetails: {token_info}"
    print(message)
    send_telegram_alert(message)

def main():
    print("[RipperBot] Starting...")
    while True:
        tokens = scan_new_tokens()
        for token in tokens:
            auto_buy(token)
        time.sleep(120)  # Wait 2 minutes between scans

if __name__ == "__main__":
    main()

