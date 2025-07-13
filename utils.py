import aiohttp
import os
import json
from datetime import datetime, timezone
import asyncio

from solders.keypair import Keypair

# --- Configuration ---
RPC_URL = os.getenv("RPC_URL", "https://api.mainnet-beta.solana.com")

private_key_env = os.getenv("PRIVATE_KEY")
if private_key_env is None:
    raise EnvironmentError("PRIVATE_KEY environment variable is not set.")
PRIVATE_KEY = json.loads(private_key_env)

BUY_AMOUNT_SOL = float(os.getenv("BUY_AMOUNT_SOL", 0.1))
SLIPPAGE = float(os.getenv("SLIPPAGE", 3))

keypair = Keypair.from_bytes(bytes(PRIVATE_KEY))

# --- Fetch recent tokens ---
async def fetch_recent_tokens():
    url = "https://api.pump.fun/tokens?sort=recent"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            if resp.status == 200:
                tokens = await resp.json()
                print(f"[DEBUG] Fetched {len(tokens)} tokens")
                return tokens
            else:
                print(f"[DEBUG] Failed to fetch tokens, status: {resp.status}")
                return []

# --- Token eligibility filter ---
def is_token_eligible(token):
    try:
        age = datetime.now(timezone.utc).timestamp() - int(token.get("timestamp", 0))
        liquidity = float(token.get("liquidity", 0))
        holders = int(token.get("uniqueHolders", 0))

        print(f"[DEBUG] Token {token.get('mint', 'unknown')} - Age: {age:.2f}s, Liquidity: {liquidity}, Holders: {holders}")

        if age < 1 or age > 180:
            print("[DEBUG] Filter reject: Token age not within 1s to 3min range")
            return False, "Token age not within 1s to 3min range"
        if liquidity < 0.3:
            print("[DEBUG] Filter reject: Low liquidity")
            return False, "Low liquidity"
        if holders < 2:
            print("[DEBUG] Filter reject: Not enough holders")
            return False, "Not enough holders"

        print("[DEBUG] Token passed filters")
        return True, ""
    except Exception as e:
        print(f"[DEBUG] Filter error: {e}")
        return False, f"Error in filter: {e}"

# --- Main async loop ---
async def main():
    tokens = await fetch_recent_tokens()
    for token in tokens:
        eligible, reason = is_token_eligible(token)
        if eligible:
            print(f"Eligible token: {token['mint']}")
        else:
            print(f"Token {token.get('mint', 'unknown')} not eligible: {reason}")

if __name__ == "__main__":
    asyncio.run(main())
