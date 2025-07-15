import os
import time
import requests
import logging

HELIUS_API_KEY = os.getenv("HELIUS_API_KEY")
HELIUS_URL = f"https://mainnet.helius-rpc.com/?api-key={HELIUS_API_KEY}"
PUMP_PROGRAM_ID = "C5pN1p7tMUT9gCgQPxz2CcsiLzgyWTu1S5Gu1w1pMxEz"
JUPITER_API_URL = "https://quote-api.jup.ag/v1/quote"

# Fetch recent token mints from the Helius API
def fetch_recent_token_mints(limit=20):
    try:
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getSignaturesForAddress",
            "params": [PUMP_PROGRAM_ID, {"limit": limit}]
        }
        response = requests.post(HELIUS_URL, json=payload)
        response.raise_for_status()
        result = response.json()
        return [tx["signature"] for tx in result.get("result", [])]
    except Exception as e:
        logging.warning(f"Failed to fetch recent token mints: {e}")
        return []

# Utility function to check if a token mint is valid
def is_valid_mint(token_data):
    if not token_data:
        return False
    try:
        return token_data.get("decimals", 0) > 0
    except Exception:
        return False

# Add other utility functions as needed here...
