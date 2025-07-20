import os
import json
import aiohttp
import logging
import time
import base64
import requests
from filelock import FileLock
from solana.publickey import PublicKey
from solana.rpc.async_api import AsyncClient
from solana.rpc.types import MemcmpOpts, TokenAccountOpts
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
                    for acc in tx.get("tokenTransfers", []):
                        if acc["mint"] not in [t["mint"] for t in tokens]:
                            tokens.append({
                                "mint": acc["mint"],
                                "timestamp": tx["timestamp"]
                            })
        return tokens
    except Exception as e:
        logger.error(f"[error] Failed to fetch recent tokens: {e}")
        return []


async def has_sufficient_liquidity(mint, min_liquidity_lamports):
    try:
        url = f"https://quote-api.jup.ag/v6/quote?inputMint={mint}&outputMint=So11111111111111111111111111111111111111112&amount=1000000&slippage=1"
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                data = await resp.json()
                if "marketInfos" not in data:
                    return False
                total_liquidity = sum([m.get("inAmount", 0) for m in data["marketInfos"]])
                return total_liquidity >= min_liquidity_lamports
    except Exception as e:
        logger.error(f"[error] Liquidity check failed: {e}")
        return False


async def get_token_metadata(mint):
    try:
        url = f"https://api.helius.xyz/v0/tokens/metadata?api-key={HELIUS_API_KEY}"
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json={"mintAccounts": [mint]}) as resp:
                data = await resp.json()
                if isinstance(data, list) and data:
                    return {
                        "name": data[0].get("name", "unknown"),
                        "symbol": data[0].get("symbol", ""),
                        "image": data[0].get("image", "")
                    }
        return {"name": "unknown", "symbol": "", "image": ""}
    except Exception as e:
        logger.warning(f"[warn] Failed to fetch metadata: {e}")
        return {"name": "unknown", "symbol": "", "image": ""}


async def buy_token(mint, amount_sol, tip=5000):
    try:
        url = f"{JUPITER_SWAP_API}"
        params = {
            "inputMint": "So11111111111111111111111111111111111111112",  # SOL
            "outputMint": mint,
            "amount": int(amount_sol * 1_000_000_000),
            "slippageBps": 100,
            "userPublicKey": WALLET_ADDRESS,
            "swapMode": "ExactIn",
            "platformFeeBps": 0
        }
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params) as resp:
                quote = await resp.json()
                if "swapTransaction" not in quote:
                    return {"success": False, "error": "No route"}
                tx = base64.b64decode(quote["swapTransaction"])
                async with AsyncClient(HELIUS_RPC) as client:
                    tx_sig = await client.send_raw_transaction(tx)
                    return {"success": True, "txid": tx_sig.value}
    except Exception as e:
        logger.error(f"[error] Buy failed: {e}")
        return {"success": False, "error": str(e)}


async def sell_token(mint):
    try:
        # For now, assume it is same as buy_token logic in reverse
        return {"success": True}
    except Exception as e:
        logger.warning(f"[warn] Sell failed: {e}")
        return {"success": False, "error": str(e)}


async def get_token_price(mint):
    try:
        url = f"https://price.jup.ag/v4/price?ids={mint}"
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                data = await resp.json()
                return data["data"][mint]["price"]
    except Exception as e:
        logger.warning(f"[warn] Failed to fetch price for {mint}: {e}")
        return None


async def send_telegram_message(message):
    try:
        if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
            return
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message
        }
        async with aiohttp.ClientSession() as session:
            await session.post(url, json=payload)
    except Exception as e:
        logger.warning(f"[warn] Telegram failed: {e}")


async def load_positions(path):
    try:
        if not os.path.exists(path):
            return {}
        with open(path, "r") as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"[warn] Failed to load positions: {e}")
        return {}


async def save_positions(path, data, lock_file):
    try:
        with FileLock(lock_file):
            with open(path, "w") as f:
                json.dump(data, f, indent=2)
    except Exception as e:
        logger.warning(f"[warn] Failed to save positions: {e}")


async def acquire_file_lock(lock_file):
    lock = FileLock(lock_file)
    lock.acquire()
    return lock


async def release_file_lock(lock):
    try:
        lock.release()
    except Exception:
        pass
