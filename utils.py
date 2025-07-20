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
JUPITER_SWAP_URL = "https://quote-api.jup.ag/v6/swap"
BUY_SLIPPAGE = float(os.getenv("BUY_SLIPPAGE", 1.0))  # 1% slippage

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

def get_token_metadata(token_address):
    """
    Placeholder function to fetch token metadata.
    Replace this logic with your actual metadata fetching implementation.
    """
    # TODO: Implement actual metadata fetching logic
    return {
        "name": "Unknown Token",
        "symbol": "UNKNOWN",
        "decimals": 0,
        "address": token_address
    }

async def buy_token(mint, amount_sol):
    try:
        async with aiohttp.ClientSession() as session:
            # Step 1: Get quote
            quote_url = (
                f"https://quote-api.jup.ag/v6/quote"
                f"?inputMint=So11111111111111111111111111111111111111112"
                f"&outputMint={mint}"
                f"&amount={int(amount_sol * 1e9)}"
                f"&slippageBps={int(BUY_SLIPPAGE * 100)}"
            )
            async with session.get(quote_url) as resp:
                quote_data = await resp.json()
            
            # Step 2: Get swap transaction
            swap_request = {
                "route": quote_data["data"][0],
                "userPublicKey": WALLET_ADDRESS,
                "wrapUnwrapSOL": True,
                "computeUnitPriceMicroLamports": 10000,
            }
            async with session.post(JUPITER_SWAP_URL, json=swap_request) as swap_resp:
                swap_data = await swap_resp.json()

            # Step 3: Send transaction to Solana
            tx_base64 = swap_data["swapTransaction"]
            # You must sign & send this tx_base64 with your wallet code
            # Placeholder:
            logger.info(f"[tx] Raw base64: {tx_base64[:20]}...")

            # TODO: Sign and send tx using Keypair or external signer
            return {"success": True, "tx": tx_base64}
    except Exception as e:
        logger.warning(f"[buy_token] Failed to buy {mint}: {e}")
        return {"success": False, "error": str(e)}
