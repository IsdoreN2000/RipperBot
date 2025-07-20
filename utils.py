import aiohttp
import asyncio
import base64
import logging
import time

MIN_AGE_SECONDS = 0
MAX_AGE_SECONDS = 3600  # 1 hour

# Replace with your actual Helius API key in environment or caller
HELIUS_URL = "https://mainnet.helius-rpc.com/?api-key=YOUR_API_KEY"

async def get_token_creation_time(mint, helius_url):
    payload = {
        "jsonrpc": "2.0", "id": 1, "method": "getAccountInfo",
        "params": [mint, {"encoding": "jsonParsed"}]
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(helius_url, json=payload, timeout=10) as resp:
                data = await resp.json()
                block_time = data.get("result", {}).get("value", {}).get("blockTime")
                if block_time:
                    return block_time
    except Exception as e:
        logging.warning(f"[get_token_creation_time] primary failed: {e}")

    payload = {
        "jsonrpc": "2.0", "id": 1, "method": "getSignaturesForAddress",
        "params": [mint, {"limit": 1}]
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(helius_url, json=payload, timeout=10) as resp:
                data = await resp.json()
                sigs = data.get("result", [])
                if sigs:
                    slot = sigs[0].get("slot")
                    if slot:
                        block_time_payload = {
                            "jsonrpc": "2.0", "id": 1, "method": "getBlockTime", "params": [slot]
                        }
                        async with session.post(helius_url, json=block_time_payload, timeout=10) as r:
                            block_data = await r.json()
                            return block_data.get("result")
    except Exception as e:
        logging.warning(f"[get_token_creation_time fallback] {e}")

    return None

async def get_recent_tokens_from_helius(program_ids):
    url = f"{HELIUS_URL.replace('/?api-key=', '/v0/addresses/')}"
    seen_mints = set()
    found = []

    async with aiohttp.ClientSession() as session:
        for program_id in program_ids:
            try:
                url_with_program = f"{url}{program_id}/transactions?limit=10"
                async with session.get(url_with_program) as resp:
                    data = await resp.json()

                    for tx in data:
                        try:
                            for event in tx.get("events", {}).get("token", []):
                                mint = event.get("mint")
                                if mint and mint not in seen_mints:
                                    seen_mints.add(mint)
                                    timestamp = tx.get("timestamp")
                                    if timestamp:
                                        found.append({
                                            "mint": mint,
                                            "timestamp": timestamp
                                        })
                        except Exception as e:
                            logging.warning(f"[parse tx failed] {e}")

            except Exception as e:
                logging.error(f"[get_recent_tokens_from_helius] Failed for {program_id}: {e}")

    return found

async def process_tokens(token_mints, helius_url):
    for mint in token_mints:
        logging.info(f"[check] {mint}")
        block_time = await get_token_creation_time(mint, helius_url)
        if not block_time:
            logging.info(f"[skip] {mint} has no block_time")
            continue

        current_time = int(time.time())
        age = current_time - block_time

        if MIN_AGE_SECONDS <= age <= MAX_AGE_SECONDS:
            logging.info(f"[buy] {mint} age: {age}s")
            # TODO: Buy logic
        else:
            logging.info(f"[skip] {mint} age: {age}s")

