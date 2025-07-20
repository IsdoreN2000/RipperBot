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
                    for acc in tx.get("tokenTransfers", []):
                        if acc["mint"] not in [t["mint"] for t in tokens]:
                            tokens.append({
                                "mint": acc["mint"],
                                "timestamp": tx["timestamp"]
