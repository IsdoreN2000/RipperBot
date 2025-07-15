import os
import aiohttp
import logging
import json
import asyncio
import random
from datetime import datetime, timezone
import requests

HELIUS_API_KEY = os.getenv("HELIUS_API_KEY")
HELIUS_URL = f"https://mainnet.helius-rpc.com/?api-key={HELIUS_API_KEY}"
PUMP_PROGRAM_ID = "C5pN1p7tMUT9gCgQPxz2CcsiLzgyWTu1S5Gu1w1pMxEz"
JUPITER_API_URL = "https://quote-api.jup.ag/v1/quote"

MIN_TOKEN_AGE_SECONDS = 180

# --- Structured JSON Logging Setup ---
class JsonFormatter(logging.Formatter):
    def format(self, record):
        log_record = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "message": record.getMessage(),
            "name": record.name,
        }
        if hasattr(record, "extra_data"):
            log_record.update(record.extra_data)
        if record.exc_info:
            log_record["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_record)

json_handler = logging.FileHandler("bot.json.log")
json_handler.setFormatter(JsonFormatter())

# Standard log setup (console + file)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    handlers=[
        logging.FileHandler("bot.log"),
        logging.StreamHandler(),
        json_handler
    ]
)

def log_with_context(level, msg, **kwargs):
    extra = {"extra_data": kwargs}
    logging.log(level, msg, extra=extra)

# --- Async Liquidity Check with Retry and Logging ---
async def has_liquidity(token_mint, retries=2):
    params = {
        "inputMint": "So11111111111111111111111111111111111111112",
        "outputMint": token_mint,
        "amount": str(int(0.01 * 1e9)),  # 0.01 SOL in lamports
        "slippageBps": 100,
    }
    for attempt in range(retries):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(JUPITER_API_URL, params=params, timeout=10) as resp:
                    if resp.status != 200:
                        log_with_context(
                            logging.WARNING,
                            f"[{resp.status}] Liquidity API for {token_mint}",
                            token_mint=token_mint,
                            status=resp.status,
                            attempt=attempt+1
                        )
                        return False
                    data = await resp.json()
                    has_route = len(data.get("data", [])) > 0
                    log_with_context(
                        logging.INFO,
                        f"[Liquidity {'OK' if has_route else 'No'}] Token: {token_mint}",
                        token_mint=token_mint,
                        has_route=has_route
                    )
                    return has_route
        except asyncio.TimeoutError:
            log_with_context(
                logging.WARNING,
                f"[Retry {attempt+1}/{retries}] Timeout for {token_mint}",
                token_mint=token_mint,
                attempt=attempt+1
            )
            await asyncio.sleep((2 ** attempt) + random.uniform(0, 1))
        except Exception as e:
            log_with_context(
                logging.WARNING,
                f"[Error] Liquidity check failed for {token_mint}: {e}",
                token_mint=token_mint,
                error=str(e),
                attempt=attempt+1
            )
            return False
    return False

# --- Fetch Recent Token Mints ---
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
        log_with_context(logging.WARNING, "Failed to fetch signatures", error=str(e))
        return []

    token_mints = []
    for sig in signatures:
        mint, ts = extract_mint_and_timestamp(sig)
        if mint and ts and is_recent(ts):
            token_mints.append(mint)
    log_with_context(logging.INFO, "Recent token mints", token_mints=token_mints)
    return token_mints

# --- Extract Mint and Timestamp from Transaction ---
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
        log_with_context(logging.WARNING, f"Error parsing transaction {signature}", error=str(e))
    return None, None

# --- Check if Token is Recent ---
def is_recent(block_time):
    if not block_time:
        return False
    now = datetime.now(timezone.utc).timestamp()
    return (now - block_time) <= MIN_TOKEN_AGE_SECONDS

# --- Main Async Batch Processing ---
async def main():
    token_mints = fetch_recent_token_mints()
    results = []
    timeout_count = 0
    success_count = 0

    for token in token_mints:
        has_liq = await has_liquidity(token)
        results.append((token, has_liq))
        if has_liq:
            success_count += 1
        else:
            timeout_count += 1

    log_with_context(
        logging.INFO,
        "Batch summary",
        total_tokens=len(token_mints),
        with_liquidity=success_count,
        without_liquidity=timeout_count
    )

if __name__ == "__main__":
    asyncio.run(main())
