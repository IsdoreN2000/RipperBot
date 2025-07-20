import aiohttp
import logging
import time
import json
import os
from dotenv import load_dotenv
from typing import List

load_dotenv()

MIN_AGE_SECONDS = 60
MAX_AGE_SECONDS = 3600  # 1 hour

async def get_token_creation_time(mint, HELIUS_URL):
    payload = {
        "jsonrpc": "2.0", "id": 1, "method": "getAccountInfo",
        "params": [mint, {"encoding": "jsonParsed"}]
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(HELIUS_URL, json=payload, timeout=10) as resp:
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
            async with session.post(HELIUS_URL, json=payload, timeout=10) as resp:
                data = await resp.json()
                sigs = data.get("result", [])
                if sigs:
                    slot = sigs[0].get("slot")
                    if slot:
                        block_time_payload = {
                            "jsonrpc": "2.0", "id": 1, "method": "getBlockTime", "params": [slot]
                        }
                        async with session.post(HELIUS_URL, json=block_time_payload, timeout=10) as r:
                            block_data = await r.json()
                            return block_data.get("result")
    except Exception as e:
        logging.warning(f"[get_token_creation_time fallback] {e}")

    return None

async def process_tokens(token_mints, HELIUS_URL):
    for mint in token_mints:
        logging.info(f"[check] {mint}")
        block_time = await get_token_creation_time(mint, HELIUS_URL)
        if not block_time:
            logging.info(f"[skip] {mint} has no block_time (API returned None)")
            continue

        current_time = int(time.time())
        age = current_time - block_time

        if MIN_AGE_SECONDS <= age <= MAX_AGE_SECONDS:
            logging.info(f"[buy] {mint} age: {age}s (within allowed window)")
            return True
        else:
            logging.info(f"[skip] {mint} age: {age}s (outside allowed window)")
            return False

def load_positions(filename="positions.json"):
    if os.path.exists(filename):
        with open(filename, "r") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return {}
    return {}

def save_positions(positions, filename="positions.json"):
    with open(filename, "w") as f:
        json.dump(positions, f, indent=2)

def format_token_url(mint):
    return f"https://solscan.io/token/{mint}"

def format_wallet_url(wallet):
    return f"https://solscan.io/account/{wallet}"

def parse_symbol_from_name(name):
    return name.split(" ")[0] if name else "N/A"
