import os
import json
import aiohttp
import logging
import time
import base64
import requests
from filelock import FileLock
from solders.pubkey import Pubkey as PublicKey
from solana.rpc.async_api import AsyncClient
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

HELIUS_API_KEY = os.getenv("HELIUS_API_KEY")
HELIUS_RPC = f"https://mainnet.helius-rpc.com/?api-key={HELIUS_API_KEY}"
JUPITER_SWAP_API = "https://quote-api.jup.ag/v6/swap"
JUPITER_TOKEN_LIST = "https://token.jup.ag/all"
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
WALLET_ADDRESS = os.getenv("WALLET_ADDRESS")

async def get_recent_tokens_from_helius(program_ids):
    url = f"https://api.helius.xyz/v0/addresses/{','.join(program_ids)}/transactions?api-key={HELIUS_API_KEY}&limit=15"
    tokens = []
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                data = await resp.json()
                for tx in data:
                    timestamp = tx.get("timestamp", int(time.time()))
                    for acc in tx.get("tokenTransfers", []):
                        if acc["mint"] not in [t["mint"] for t in tokens]:
                            tokens.append({
                                "mint": acc["mint"],
                                "timestamp": timestamp
                            })
        return tokens
    except Exception as e:
        logger.warning(f"Failed to fetch recent tokens: {e}")
        return []

async def has_sufficient_liquidity(mint, min_liquidity):
    try:
        async with aiohttp.ClientSession() as session:
            url = f"https://quote-api.jup.ag/v6/pools?inputMint={mint}"
            async with session.get(url) as resp:
                data = await resp.json()
                for pool in data.get("pools", []):
                    if pool.get("inputMint") == mint and pool.get("liquidity", 0) >= min_liquidity:
                        return True
        return False
    except Exception as e:
        logger.warning(f"Liquidity check failed for {mint}: {e}")
        return False

async def get_token_metadata(mint):
    try:
        url = f"https://api.helius.xyz/v0/tokens/metadata?api-key={HELIUS_API_KEY}"
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json={"mintAccounts": [mint]}) as resp:
                result = await resp.json()
                metadata = result[0] if result else {}
                return {
                    "name": metadata.get("name", "Unknown"),
                    "symbol": metadata.get("symbol", ""),
                    "image": metadata.get("image", "")
                }
    except Exception as e:
        logger.warning(f"Metadata fetch failed for {mint}: {e}")
        return {
            "name": "Unknown",
            "symbol": "",
            "image": ""
        }

async def buy_token(mint, amount_sol, tip=5000):
    # Placeholder buy simulation
    try:
        logger.info(f"Simulating buy for {mint} of {amount_sol} SOL with tip {tip}")
        await asyncio.sleep(1)
        return {"success": True}
    except Exception as e:
        logger.warning(f"Buy failed: {e}")
        return {"success": False, "error": str(e)}

async def get_token_price(mint):
    try:
        url = f"https://price.jup.ag/v4/price?ids={mint}"
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                data = await resp.json()
                return data.get(mint, {}).get("price")
    except Exception as e:
        logger.warning(f"Price fetch failed for {mint}: {e}")
        return None

async def sell_token(mint):
    try:
        logger.info(f"Simulating sell for {mint}")
        await asyncio.sleep(1)
        return True
    except Exception as e:
        logger.warning(f"Sell failed for {mint}: {e}")
        return False

async def send_telegram_message(message):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message}
        requests.post(url, json=payload)
    except Exception as e:
        logger.warning(f"Telegram message failed: {e}")
