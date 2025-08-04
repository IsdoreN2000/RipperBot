import asyncio
import logging
import time
import json
from utils import (
    get_recent_tokens_from_dbotx,
    has_sufficient_liquidity,
    get_token_metadata,
    buy_token,
    get_token_price,
    sell_token,
    send_telegram_message,
    listen_to_dbotx_trades
)
import aiohttp
import os

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

POSITIONS_FILE = "positions.json"
MAX_TOKEN_AGE = 360  # seconds
MIN_LIQUIDITY_SOL = 20
BUY_AMOUNT_SOL = 5
PROFIT_TARGET = 2.0  # 2x
STOP_LOSS = 0.5      # 50%

positions = {}


def load_positions():
    global positions
    if os.path.exists(POSITIONS_FILE):
        with open(POSITIONS_FILE, "r") as f:
            try:
                positions.update(json.load(f))
            except Exception as e:
                logger.warning(f"[load] Failed to load positions file: {e}")
    else:
        positions.clear()


def save_positions():
    try:
        with open(POSITIONS_FILE, "w") as f:
            json.dump(positions, f, indent=2)
    except Exception as e:
        logger.warning(f"[save] Failed to write positions file: {e}")


async def monitor_positions():
    while True:
        try:
            for mint in list(positions.keys()):
                entry = positions[mint]
                bought_price = entry["buy_price"]
                symbol = entry.get("symbol", "?")
                price = await get_token_price(mint)

                if price == 0:
                    logger.warning(f"[price] {mint} returned price 0, skipping")
                    continue

                if price >= bought_price * PROFIT_TARGET:
                    logger.info(f"[sell] Profit target hit for {mint}")
                    await sell_token(mint)
                    await send_telegram_message(f"✅ Sold {symbol} ({mint[:5]}...) for profit!")
                    del positions[mint]
                    save_positions()

                elif price <= bought_price * STOP_LOSS:
                    logger.info(f"[sell] Stop-loss triggered for {mint}")
                    await sell_token(mint)
                    await send_telegram_message(f"🛑 Sold {symbol} ({mint[:5]}...) due to stop-loss.")
                    del positions[mint]
                    save_positions()

        except Exception as e:
            logger.warning(f"[monitor error] {e}")
        await asyncio.sleep(15)


async def process_tokens():
    async with aiohttp.ClientSession() as session:
        tokens = await get_recent_tokens_from_dbotx(session)
        logger.info(f"[main] Fetched {len(tokens)} tokens")

        for token in tokens:
            mint = token.get("mint")
            timestamp = token.get("timestamp")

            if not mint or not timestamp:
                continue

            if mint in positions:
                continue

            age = time.time() - timestamp
            logger.info(f"[check] {mint} age={int(age)}s")

            if age > MAX_TOKEN_AGE:
                logger.info(f"[skip] {mint} too old ({int(age)}s)")
                continue

            if not await has_sufficient_liquidity(mint, MIN_LIQUIDITY_SOL * 1_000_000_000):
                logger.info(f"[skip] {mint} - low liquidity")
                continue

            metadata = await get_token_metadata(mint)
            symbol = metadata.get("symbol", "?")

            buy_result = await buy_token(mint, BUY_AMOUNT_SOL)
            if buy_result.get("success"):
                price = await get_token_price(mint)
                if price > 0:
                    positions[mint] = {
                        "buy_price": price,
                        "symbol": symbol
                    }
                    save_positions()
                    await send_telegram_message(f"🛒 Bought {symbol} ({mint[:5]}...) @ {price:.6f}")
                else:
                    logger.warning(f"[price] Failed to fetch price for {mint} after buying")
            else:
                logger.warning(f"[buy failed] {mint}")


async def main_loop():
    while True:
        try:
            await process_tokens()
        except Exception as e:
            logger.warning(f"[loop error] {e}")
        await asyncio.sleep(10)


async def main():
    load_positions()
    await asyncio.gather(
        listen_to_dbotx_trades(),
        main_loop(),
        monitor_positions()
    )


if __name__ == "__main__":
    asyncio.run(main())
