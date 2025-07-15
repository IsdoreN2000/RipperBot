import os
import json
import base64
import aiohttp
import logging
from datetime import datetime, timezone
from solders.keypair import Keypair
from solders.transaction import VersionedTransaction
from solana.rpc.async_api import AsyncClient
from solana.rpc.types import TxOpts
import asyncio

logging.basicConfig(level=logging.INFO)

# --- Helius RPC Setup ---
HELIUS_KEY = os.getenv("HELIUS_API_KEY")
if not HELIUS_KEY:
    raise EnvironmentError("❌ HELIUS_API_KEY environment variable is not set.")
RPC_URL = f"https://mainnet.helius-rpc.com/?api-key={HELIUS_KEY}"

private_key_env = os.getenv("PRIVATE_KEY")
if private_key_env is None:
    raise EnvironmentError("PRIVATE_KEY environment variable is not set.")
PRIVATE_KEY = json.loads(private_key_env)
keypair = Keypair.from_bytes(bytes(PRIVATE_KEY))

BUY_AMOUNT_SOL = float(os.getenv("BUY_AMOUNT_SOL", 0.1))
SLIPPAGE = float(os.getenv("SLIPPAGE", 3))
JUPITER_API_URL = "https://quote-api.jup.ag/v1/quote"

async def fetch_recent_tokens():
    url = "https://api.pump.fun/tokens?sort=recent"
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url, timeout=10) as resp:
                if resp.status == 200:
                    tokens = await resp.json()
                    logging.info(f"Fetched {len(tokens)} tokens")
                    return tokens
                else:
                    logging.warning(f"Failed to fetch tokens, status: {resp.status}")
                    return []
        except Exception as e:
            logging.error(f"Error fetching tokens: {e}")
            return []

def is_token_eligible(token, max_age_seconds=600):
    """
    Returns True if the token is younger than max_age_seconds.
    Expects token to have a 'created_at', 'createdAt', or 'timestamp' field.
    """
    try:
        # Adjust the key according to the actual API response
        created_at = token.get("created_at") or token.get("createdAt") or token.get("timestamp")
        if not created_at:
            return False
        # If the timestamp is in milliseconds, convert to seconds
        if created_at > 1e12:
            created_at = created_at / 1000
        age = datetime.now(timezone.utc).timestamp() - float(created_at)
        return age < max_age_seconds
    except Exception as e:
        logging.error(f"Error checking token eligibility: {e}")
        return False

# --- Example usage ---
async def main():
    tokens = await fetch_recent_tokens()
    eligible_tokens = [t for t in tokens if is_token_eligible(t)]
    logging.info(f"Eligible tokens: {len(eligible_tokens)}")
    for token in eligible_tokens:
        logging.info(f"Eligible token: {token.get('mint', 'unknown')}")

if __name__ == "__main__":
    asyncio.run(main())
