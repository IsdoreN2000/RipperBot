import os
import json
import aiohttp
import logging
import time
import requests
from filelock import FileLock
from solders.pubkey import Pubkey
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
    tokens = []
    for program_id in program_ids:
        url = f"https://api.helius.xyz/v0/addresses/{program_id}/transactions?api-key={HELIUS_API_KEY}&limit=10"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as resp:
                    logger.warning(f"Helius API status for {program_id}: {resp.status}")
                    text = await resp.text()
                    logger.warning(f"Helius API raw response: {text}")
                    try:
                        data = await resp.json(content_type=None)
                    except Exception as json_err:
                        logger.warning(f"Failed to parse JSON: {json_err}")
                        continue

                    if not isinstance(data, list):
                        logger.warning(f"Unexpected data format for {program_id}: {data}")
                        continue

                    for tx in data:
                        timestamp = tx.get("timestamp", int(time.time()))
                        for acc in tx.get("tokenTransfers", []):
                            if acc["mint"] not in [t["mint"] for t in tokens]:
                                tokens.append({
                                    "mint": acc["mint"],
                                    "amount": acc.get("amount"),
                                    "source": acc.get("source"),
                                    "destination": acc.get("destination"),
                                    "timestamp": timestamp
                                })
        except Exception as e:
            logger.warning(f"Error fetching tokens for {program_id}: {e}")
    return tokens

def has_sufficient_liquidity(token, amount):
    """
    Placeholder function to check if a token has sufficient liquidity.
    Replace this logic with your actual liquidity check.
    """
    # TODO: Implement actual liquidity check logic
    return True
