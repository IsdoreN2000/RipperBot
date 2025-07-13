import aiohttp
import os
import base64
import json
from datetime import datetime, timezone

from solders.keypair import Keypair
from solders.pubkey import Pubkey
from solders.transaction import VersionedTransaction
from solana.rpc.async_api import AsyncClient
from solana.rpc.types import TxOpts

# You'll need to implement or wrap the pump-swap-sdk logic here:
from pump_swap import create_buy_txn, create_sell_txn

RPC_URL = os.getenv("RPC_URL", "https://api.mainnet-beta.solana.com")
PRIVATE_KEY = json.loads(os.getenv("PRIVATE_KEY"))
BUY_AMOUNT_SOL = float(os.getenv("BUY_AMOUNT_SOL", 0.1))
SLIPPAGE = float(os.getenv("SLIPPAGE", 3))

client = AsyncClient(RPC_URL)
keypair = Keypair.from_bytes(bytes(PRIVATE_KEY))


async def fetch_recent_tokens():
    url = "https://api.pump.fun/tokens?sort=recent"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            if resp.status == 200:
                return await resp.json()
            else:
                return []


def is_token_eligible(token):
    try:
        age = datetime.now(timezone.utc).timestamp() - int(token.get("timestamp", 0))
        liquidity = float(token.get("liquidity", 0))
        holders = int(token.get("uniqueHolders", 0))

        if age > 60:
            return False, "Too old"
        if liquidity < 0.3:
            return False, "Low liquidity"
        if holders < 2:
            return False, "Not enough holders"

        return True, "Eligible"
    except Exception as e:
        return False, f"Eligibility check error: {e}"
