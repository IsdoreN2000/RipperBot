import asyncio
import os
import time
from datetime import datetime, timezone

from utils import (
    fetch_recent_tokens,
    is_token_eligible,
    execute_buy,
    execute_sell,
    send_telegram_message,
)
from telegram import handle_command

SEEN_TOKENS = set()
BUY_AMOUNT_SOL = float(os.getenv("BUY_AMOUNT_SOL", 0.1))
SCAN_INTERVAL = 2.5  # seconds
AUTO_SELL_MULTIPLIER = float(os.getenv("AUTO_SELL_MULTIPLIER", 2.0))


def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")


async def sniper_loop():
    while True:
        try:
            tokens = await fetch_recent_tokens()
            for token in tokens:
                mint = token.get("mint")
                if mint in SEEN_TOKENS:
                    continue

                SEEN_TOKENS.add(mint)
                eligible, reason = is_token_eligible(token)

                if eligible:
                    log(f"✅ Eligible token found: {token['symbol']} ({mint})")
                    await send_telegram_message(
                        f"🎯 *BUY SIGNAL*\nToken: {token['symbol']}\nMint: {mint}"
                        # Ensure your send_telegram_message sets parse_mode="Markdown" or "MarkdownV2"
                    )
                    success, tx = await execute_buy(mint)
                    if success:
                        await send_telegram_message(
                            f"✅ *Buy Executed*\n[View TX](https://solscan.io/tx/{tx})"
                        )

                        log(f"⏳ Waiting to auto-sell if {AUTO_SELL_MULTIPLIER}x target hit...")
                        sell_success, sell_tx = await execute_sell(mint, multiplier=AUTO_SELL_MULTIPLIER)
                        if sell_success:
                            await send_telegram_message(
                                f"💸 *Auto-Sold* at {AUTO_SELL_MULTIPLIER}×\n[TX](https://solscan.io/tx/{sell_tx})"
                            )
                        else:
                            await send_telegram_message(
                                f"⚠️ *Auto-Sell Failed* for {mint}"
                            )
                    else:
                        await send_telegram_message(
                            f"⚠️ *Buy Failed* for {token['symbol']}"
                        )
                else:
                    log(f"⏩ Skipped {token['symbol']}: {reason}")

        except Exception as e:
            log(f"❌ Error: {e}")
            await send_telegram_message(f"❌ *Bot Error:* {e}")

        await asyncio.sleep(SCAN_INTERVAL)


async def main():
    await asyncio.gather(
        sniper_loop(),
        handle_command(),
    )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        log(f"❌ Fatal Error: {e}")

