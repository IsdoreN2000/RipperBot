import asyncio
import aiohttp
import logging
import json
import os
import time
from typing import Dict, Any
from flask import Flask, request

from utils import execute_buy, send_telegram_message, execute_sell, get_token_price

POSITIONS_FILE = "positions.json"
positions: Dict[str, Any] = {}  # {mint: {buy_price, tx, timestamp}}

# --- Logging setup ---
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

app = Flask(__name__)

def load_positions():
    global positions
    if os.path.exists(POSITIONS_FILE):
        try:
            with open(POSITIONS_FILE, "r") as f:
                positions = json.load(f)
            logging.info("✅ Positions loaded.")
        except Exception as e:
            logging.error(f"Failed to load positions: {e}")

def save_positions():
    try:
        tmp_file = POSITIONS_FILE + ".tmp"
        with open(tmp_file, "w") as f:
            json.dump(positions, f)
        os.replace(tmp_file, POSITIONS_FILE)
        logging.info("✅ Positions saved.")
    except Exception as e:
        logging.error(f"Failed to save positions: {e}")

@app.route('/new-pool', methods=['POST'])
def new_pool():
    data = request.json
    base_mint = data.get("baseMint")
    quote_mint = data.get("quoteMint")
    logging.info(f"🚨 New Raydium pool received: base={base_mint}, quote={quote_mint}")
    # Trigger your buy logic asynchronously
    asyncio.get_event_loop().create_task(handle_new_pool(base_mint))
    return {"status": "ok"}

async def handle_new_pool(mint):
    load_positions()
    if mint in positions:
        logging.info(f"Already bought {mint}, skipping.")
        return
    try:
        await send_telegram_message(f"🚀 Raydium Auto-buy: {mint}")
        success, tx = await execute_buy(mint, amount_usd=5)
        if success:
            price = await get_token_price(mint)
            positions[mint] = {
                "buy_price": price,
                "tx": tx,
                "timestamp": time.time()
            }
            save_positions()
            await send_telegram_message(f"✅ Raydium Bought: {mint} at ${price:.4f}\nTx: {tx}")
        else:
            await send_telegram_message(f"❌ Raydium Buy failed: {mint}")
    except Exception as e:
        logging.error(f"Error buying {mint}: {e}")
        await send_telegram_message(f"❌ Raydium Error buying {mint}: {e}")

async def monitor_prices():
    load_positions()
    logging.info("📈 Raydium price monitor started.")
    while True:
        to_remove = []
        for mint, data in positions.items():
            try:
                buy_price = float(data["buy_price"])
                current_price = await get_token_price(mint)
                if current_price >= buy_price * 2:
                    await send_telegram_message(f"💰 Selling {mint} at 2x: ${current_price:.4f}")
                    success, tx = await execute_sell(mint)
                    if success:
                        await send_telegram_message(f"✅ Sold {mint}\nTx: {tx}")
                        to_remove.append(mint)
                    else:
                        await send_telegram_message(f"❌ Sell failed for {mint}")
            except Exception as e:
                logging.error(f"Sell check failed for {mint}: {e}")
        for mint in to_remove:
            positions.pop(mint, None)
        if to_remove:
            save_positions()
        await asyncio.sleep(60)

def start_monitor():
    loop = asyncio.get_event_loop()
    loop.create_task(monitor_prices())
    app.run(host="0.0.0.0", port=5000)

if __name__ == "__main__":
    start_monitor()
