import time
import requests
import logging

HELIUS_API_KEY = os.getenv("HELIUS_API_KEY")
HELIUS_URL = f"https://mainnet.helius-rpc.com/?api-key={HELIUS_API_KEY}"
PUMP_PROGRAM_ID = "C5pN1p7tMUT9gCgQPxz2CcsiLzgyWTu1S5Gu1w1pMxEz"

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
        tx_signatures = [tx["signature"] for tx in response.json().get("result", [])]
    except Exception as e:
        logging.warning(f"Failed to fetch signatures: {e}")
        return []

    mint_addresses = []

    for signature in tx_signatures:
        try:
            tx_payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "getTransaction",
                "params": [signature, {
                    "encoding": "jsonParsed",
                    "maxSupportedTransactionVersion": 0
                }]
            }
            tx_resp = requests.post(HELIUS_URL, json=tx_payload)
            tx_resp.raise_for_status()
            result = tx_resp.json().get("result", {})

            # Check token age
            block_time = result.get("blockTime")
            if not block_time:
                continue
            age_seconds = time.time() - block_time
            if age_seconds < 180:
                continue

            # Extract mint from postTokenBalances
            post_token_balances = result.get("meta", {}).get("postTokenBalances", [])
            for token in post_token_balances:
                mint = token.get("mint")
                if mint and mint not in mint_addresses:
                    mint_addresses.append(mint)

        except Exception as e:
            logging.warning(f"Failed to parse tx {signature}: {e}")
            continue

    return mint_addresses
