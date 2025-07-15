import asyncio
import logging
from datetime import datetime, timezone

from utils import (
    fetch_recent_token_mints,
    has_liquidity,
    execute_buy,
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_CHAT_ID,
    send_telegram_message,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Constants
MIN_TOKEN_AGE_SECONDS = 180  # Minimum token age to avoid honeypots
POLL_INTERVAL_SECONDS = 5

# Track processed tokens
seen_tokens = set()

async def process_tokens():
    while True:
        try:
            logger.info("Fetching recent token mints...")
            token_mints = await fetch_recent_token_mints()
            logger.info(f"Recent token mints: {token_mints}")

            for token_data in token_mints:
                mint = token_data.get("mint")
                created_at = token_data.get("created_at")

                if not mint or not created_at:
                    logger.info(f"Skipped token {mint}: Missing or invalid mint")
                    continue

                if mint in seen_tokens:
                    continue

                # Token age filter
                now = datetime.now(timezone.utc).timestamp()
                token_age = now - created_at
                if token_age < MIN_TOKEN_AGE_SECONDS:
                    logger.info(f"Skipped token {mint}: Age {token_age:.2f}s < {MIN_TOKEN_AGE_SECONDS}s")
                    continue

                # Check liquidity
                try:
                    has_pool = await has_liquidity(mint)
                except Exception as e:
                    logger.warning(f"Liquidity check failed for {mint}: {e}")
                    logger.info(f"Skipped token {mint}: No liquidity pool found.")
                    continue

                if not has_pool:
                    logger.info(f"Skipped token {mint}: No liquidity pool found.")
                    continue

                # Execute buy
                logger.info(f"Attempting to buy token {mint}...")
                try:
                    success = await execute_buy(mint)
                    if success:
                        seen_tokens.add(mint)
                        await send_telegram_message(
                            TELEGRAM_BOT_TOKEN,
                            TELEGRAM_CHAT_ID,
                            f"✅ Successfully bought token: {mint}"
                        )
                    else:
                        logger.error(f"Buy failed for {mint}")
                except Exception as e:
                    logger.error(f"execute_buy failed for {mint}: {e}")

        except Exception as e:
            logger.error(f"Error in process loop: {e}")

        await asyncio.sleep(POLL_INTERVAL_SECONDS)

if __name__ == "__main__":
    logger.info("=== BOT.PY STARTED ===")
    asyncio.run(process_tokens())
