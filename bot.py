import os
import requests
from dotenv import load_dotenv

load_dotenv()

HELIUS_API_KEY = os.getenv("HELIUS_API_KEY")
HELIUS_URL = f"https://mainnet.helius-rpc.com/?api-key={HELIUS_API_KEY}"
PUMP_PROGRAM_ID = "C5pN1p7tMUT9gCgQPxz2CcsiLzgyWTu1S5Gu1w1pMxEz"

def get_recent_signatures(limit=5):
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
        if "result" not in result:
            raise ValueError("Invalid response from Helius")
        return [tx["signature"] for tx in result["result"]]
    except Exception as e:
        print(f"Error fetching signatures: {e}")
        return []

def get_token_mints_from_tx(signature):
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "getTransaction",
        "params": [signature, {"encoding": "jsonParsed"}]
    }
    try:
        response = requests.post(HELIUS_URL, json=payload)
        response.raise_for_status()
        result = response.json()
        if "result" not in result or not result["result"]:
            return []
        tx = result["result"]["transaction"]
        mints = set()
        # Parse all instructions for mint addresses
        for instr in tx["message"]["instructions"]:
            if "parsed" in instr and "info" in instr["parsed"]:
                info = instr["parsed"]["info"]
                if "mint" in info:
                    mints.add(info["mint"])
        return list(mints)
    except Exception as e:
        print(f"Error fetching transaction {signature}: {e}")
        return []

def get_recent_token_mints(limit=5):
    signatures = get_recent_signatures(limit)
    all_mints = set()
    for sig in signatures:
        mints = get_token_mints_from_tx(sig)
        all_mints.update(mints)
    return list(all_mints)

if __name__ == "__main__":
    recent_token_mints = get_recent_token_mints(5)
    print("Recent token mints:", recent_token_mints)
