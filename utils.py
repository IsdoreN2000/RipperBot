import os
import json
import time
import base64
import aiohttp
import logging
from datetime import datetime, timezone

from solana.rpc.async_api import AsyncClient
from solana.rpc.types import MemcmpOpts, TokenAccountOpts

logging.basicConfig(level=logging.INFO)

JUPITER_API_URL = "https://quote-api.jup.ag/v1/quote"
INPUT_MINT = "So11111111111111111111111111111111111111112"  # Wrapped SOL

async def get_token_mints_from_tx(signature, session, helius_url):
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "getTransaction",
        "params": [signature, {
            "encoding": "jsonParsed",
            "maxSupportedTransactionVersion": 0  # fixes error
        }]
    }
    try:
        async with session.post(helius_url, json=payload, timeout=10) as resp:
            result = await resp.json()
            logging.debug(f"getTransaction result for {signature}: {result}")
            tx = result.get("result", {}).get("transaction", {})
            mints = set()
            for instr in tx.get("message", {}).get("instructions", []):
                if "parsed" in instr and "info" in instr["parsed"]:
                    info = instr["parsed"]["info"]
                    if "mint" in info:
                        mint = info["mint"]
                        if mint.endswith("pump"):
                            mints.add(mint)
            return list(mints)
    except Exception as e:
        logging.warning(f"Failed to parse mints from {signature}: {e}")
        return []

async def has_liquidity(input_mint, output_mint, amount=10000000, slippage=3):
    params = {
        "inputMint": input_mint,
        "outputMint": output_mint,
        "amount": str(amount),
        "slippage": str(slippage)
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(JUPITER_API_URL, params=params, timeout=10) as resp:
                data = await resp.json()
                if "data" in data and len(data["data"]) > 0:
                    return True
    except Exception as e:
        logging.warning(f"Liquidity check failed for {output_mint}: {e}")
    return False

async def get_token_creation_time(mint_address, helius_url):
    url = helius_url
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "getSignaturesForAddress",
        "params": [mint_address, {"limit": 1}]
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, timeout=10) as resp:
                result = await resp.json()
                sigs = result.get("result", [])
                if len(sigs) > 0:
                    block_time = sigs[0].get("blockTime", 0)
                    return block_time
    except Exception as e:
        logging.warning(f"Token creation time fetch failed for {mint_address}: {e}")
    return 0

def is_token_old_enough(created_at_unix, min_age_sec=180):
    now = int(time.time())
    age = now - created_at_unix
    return age >= min_age_sec
