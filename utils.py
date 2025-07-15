import os
import json
import base64
import aiohttp
import logging
from datetime import datetime, timezone
from solders.keypair import Keypair
from solders.transaction import VersionedTransaction
from solana.rpc.async_api import AsyncClient
from solana.rpc.types import TxOpts
import asyncio
import requests

logging.basicConfig(level=logging.INFO)

print("Script started")  # Confirm script is running

# Load environment variables
RPC_URL = os.getenv("RPC_URL", "https://mainnet.helius-rpc.com/?api-key=" + os.getenv("HELIUS_API_KEY"))
PRIVATE_KEY = json.loads(os.getenv("PRIVATE_KEY"))
keypair = Keypair.from_bytes(bytes(PRIVATE_KEY))

BUY_AMOUNT_SOL = float(os.getenv("BUY_AMOUNT_SOL", 0.1))
SLIPPAGE = float(os.getenv("SLIPPAGE", 3))
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
HELIUS_API_KEY = os.getenv("HELIUS_API_KEY")
HELIUS_URL = f"https://mainnet.helius-rpc.com/?api-key={HELIUS_API_KEY}"
PUMP_PROGRAM_ID = "C5pN1p7tMUT9gCgQPxz2CcsiLzgyWTu1S5Gu1w1pMxEz"
JUPITER_API_URL = "https://quote-api.jup.ag/v1/quote"

# === HELIUS TX FETCHING ===
def get_recent_signatures(limit=20):
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "getSignaturesForAddress",
        "params": [PUMP_PROGRAM_ID, {"limit": limit}]
    }
    try:
        response = requests.post(HELIUS_URL, json=payload)
        response.raise_for_status()
        result = response.json()
        print("DEBUG: getSignaturesForAddress result:", result)
        return [tx["signature"] for tx in result.get("result", [])]
    except Exception as e:
        print("DEBUG: Exception in get_recent_signatures:", e)
        logging.warning(f"Failed to fetch signatures: {e}")
        return []

def get_token_mints_from_tx(signature):
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "getTransaction",
        "params": [signature, {
            "encoding": "jsonParsed",
            "maxSupportedTransactionVersion": 0  # ✅ FIXED LINE
        }]
    }
    try:
        response = requests.post(HELIUS_URL, json=payload)
        response.raise_for_status()
        result = response.json()
        print(f"DEBUG: getTransaction result for {signature}:", result)
        tx = result.get("result", {}).get("transaction", {})
        mints = set()
        for instr in tx.get("message", {}).get("instructions", []):
            if "parsed" in instr and "info" in instr["parsed"]:
                info = instr["parsed"]["info"]
                if
