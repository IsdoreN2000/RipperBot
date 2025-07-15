import os
import aiohttp
import logging
import asyncio
from datetime import datetime, timezone
import requests

HELIUS_API_KEY = os.getenv("HELIUS_API_KEY")
HELIUS_URL = f"https://mainnet.helius-rpc.com/?api-key={HELIUS_API_KEY}"
PUMP_PROGRAM_ID = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
JUPITER_API_URL = "https://quote-api.jup.ag/v1/quote"

MIN_TOKEN_AGE_SECONDS = 40

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

async def has_liquidity(token_mint):
    params = {
        "inputMint": "So11111111111111111111111111111111111111112",
        "outputMint": token_mint,
        "amount": str(int(0.01 * 1e9)),  # 0.01 SOL in lamports
        "slippageBps": 100,
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(JUPITER_API_URL, params=params, timeout=10) as resp:
                if resp.status != 200:
                    logging.warning(f"Liquidity check failed for {token_mint}: HTTP {resp.status}")
                    return False
                data = await resp.json()
                has_route = len(data.get("data", [])) > 0
                logging.info(f"Liquidity {'OK' if has_route else 'NO'} for {token_mint}")
                return has_route
    except Exception as e:
        logging.warning(f"Liquidity check failed for {token_mint}: {e}")
        return False

def fetch_recent_token_mints(limit=20):
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "getSignaturesForAddress",
        "params": [PUMP_PROGRAM_ID, {"limit": limit}]
    }
    try:
        response = requests.post(HELIUS_URL, json=payload)
        response.raise_for_status()
        signatures = [tx["signature"] for tx in response.json().get("result", [])]
    except Exception as e:
        logging.warning(f"Failed to fetch signatures: {e}")
        return []

    token_mints = []
    for sig in signatures:
        mint, ts = extract_mint_and_timestamp(sig)
        if mint and ts and is_recent(ts):
            token_mints.append(mint)
    logging.info(f"Recent token mints: {token_mints}")
    return token_mints

def extract_mint_and_timestamp(signature):
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "getTransaction",
        "params": [signature, {"encoding": "jsonParsed"}]
    }
    try:
        response = requests.post(HELIUS_URL, json=payload)
        response.raise_for_status()
        result = response.json().get("result", {})
        block_time = result.get("blockTime")
        tx = result.get("transaction", {})
        message = tx.get("message", {})
        instructions = message.get("instructions", [])

        for instr in instructions:
            if "parsed" in instr and "info" in instr["parsed"]:
                info = instr["parsed"]["info"]
                mint = info.get("mint")
                if mint:
                    return mint, block_time
    except Exception as e:
        logging.warning(f"Error parsing transaction {signature}: {e}")
    return None, None

def is_recent(block_time):
    if not block_time:
        return False
    now = datetime.now(timezone.utc).timestamp()
    return (now - block_time) <= MIN_TOKEN_AGE_SECONDS

async def main():
    token_mints = fetch_recent_token_mints()
    with_liquidity = 0
    without_liquidity = 0

    for token in token_mints:
        has_liq = await has_liquidity(token)
        if has_liq:
            with_liquidity += 1
        else:
            without_liquidity += 1

    logging.info(
        f"Batch summary: {with_liquidity} with liquidity, {without_liquidity} without liquidity, out of {len(token_mints)} tokens"
    )

if __name__ == "__main__":
    asyncio.run(main())
