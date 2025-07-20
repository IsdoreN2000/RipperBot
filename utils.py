import aiohttp
import aiofiles
import json
import os
import base64
import logging
from datetime import datetime, timezone
from solders.pubkey import Pubkey
from solana.rpc.async_api import AsyncClient
from solana.rpc.types import TokenAccountOpts
from filelock import FileLock

# Helius settings
HELIUS_API_KEY = os.getenv("HELIUS_API_KEY")
HELIUS_URL = f"https://mainnet.helius.xyz/v0/addresses"

# Token Program ID (SPL)
TOKEN_PROGRAM_ID = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"

# Jupiter swap settings
JUPITER_QUOTE_API = "https://quote-api.jup.ag/v6/quote"
JUPITER_SWAP_API = "https://quote-api.jup.ag/v6/swap"
RPC_URL = os.getenv("RPC_URL", "https://api.mainnet-beta.solana.com")

# Telegram
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# Wallet
WALLET = os.getenv("WALLET")


async def get_recent_tokens_from_helius(program_ids, limit=25):
    headers = {"Content-Type": "application/json"}
    tokens = []
    for program_id in program_ids:
        url = f"https://api.helius.xyz/v0/addresses/{program_id}/transactions?api-key={HELIUS_API_KEY}"
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                data = await resp.json()
                for tx in data:
                    if 'tokenTransfers' in tx:
                        for transfer in tx['tokenTransfers']:
                            if transfer['tokenAmount'] and transfer['mint']:
                                timestamp = tx['timestamp']
                                tokens.append({
                                    "mint": transfer['mint'],
                                    "timestamp": timestamp
                                })
    return tokens


async def has_sufficient_liquidity(mint: str, min_liquidity_lamports: int) -> bool:
    url = f"https://public-api.birdeye.so/public/pair/mint/{mint}"
    headers = {"X-API-KEY": os.getenv("BIRDEYE_API_KEY")}
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as resp:
            if resp.status != 200:
                return False
            data = await resp.json()
            try:
                liquidity = data['data']['liquidity']['base'] + data['data']['liquidity']['quote']
                return liquidity >= min_liquidity_lamports
            except:
                return False


async def get_token_metadata(mint: str):
    url = f"https://api.helius.xyz/v0/tokens/metadata?api-key={HELIUS_API_KEY}"
    body = {"mints": [mint]}
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=body) as resp:
            result = await resp.json()
            if result and isinstance(result, list):
                return result[0]
    return {"name": "Unknown", "symbol": "UNK"}


async def buy_token(mint: str, amount_sol: float, tip: int = 5000):
    # Simulated buy logic
    return {"success": True}


async def sell_token(mint: str):
    # Simulated sell logic
    return {"success": True}


async def get_token_price(mint: str):
    url = f"https://public-api.birdeye.so/public/price?address={mint}"
    headers = {"X-API-KEY": os.getenv("BIRDEYE_API_KEY")}
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as resp:
            if resp.status == 200:
                data = await resp.json()
                return data.get("data", {}).get("value", None)
    return None


async def send_telegram_message(text: str):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {"chat_id": TELEGRAM_CHAT_ID, "text": text}
    async with aiohttp.ClientSession() as session:
        await session.post(url, data=data)


async def load_positions(filename: str) -> dict:
    try:
        async with aiofiles.open(filename, mode='r') as f:
            content = await f.read()
            return json.loads(content)
    except:
        return {}


async def save_positions(filename: str, positions: dict, lockfile: str):
    lock = FileLock(lockfile)
    async with lock:
        async with aiofiles.open(filename, mode='w') as f:
            await f.write(json.dumps(positions))


async def acquire_file_lock(lockfile: str):
    lock = FileLock(lockfile)
    await lock.acquire()


async def release_file_lock(lockfile: str):
    lock = FileLock(lockfile)
    if lock.is_locked:
        await lock.release()
