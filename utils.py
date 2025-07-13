import aiohttp
import os
import json
from datetime import datetime, timezone

from solders.keypair import Keypair
from solders.pubkey import Pubkey
from solders.transaction import VersionedTransaction
from solana.rpc.async_api import AsyncClient
from solana.rpc.types import TxOpts

# TEMP placeholder (replace with actual SDK integration)
async def create_buy_txn(*args, **kwargs):
    raise NotImplementedError("pump_swap.create_buy_txn not implemented yet")

async def create_sell_txn(*args, **kwargs):
    raise NotImplementedError("pump_swap.create_sell_txn not implemented yet")

RPC_URL = os.getenv("RPC_URL", "https://api.mainnet-beta.solana.com")

private_key_env = os.getenv("PRIVATE_KEY")
if private_key_env is None:
    raise EnvironmentError("PRIVATE_KEY environment variable is not set.")
PRIVATE_KEY = json.loads(private_key_env)

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

        return True, ""
    except Exception as e:
        return False, f"Error in filter: {e}"


async def execute_buy(mint):
    try:
        txn = await create_buy_txn(client, keypair, Pubkey.from_string(mint), BUY_AMOUNT_SOL, SLIPPAGE)
        sig = await client.send_raw_transaction(txn.serialize(), opts=TxOpts(skip_preflight=True))
        return True, str(sig.value)
    except Exception as e:
        print("Buy failed:", e)
        return False, None


async def execute_sell(mint, multiplier=2.0):
    try:
        txn = await create_sell_txn(client, keypair, Pubkey.from_string(mint), multiplier)
        sig = await client.send_raw_transaction(txn.serialize(), opts=TxOpts(skip_preflight=True))
        return True, str(sig.value)
    except Exception as e:
        print("Sell failed:", e)
        return False, None


async def send_telegram_message(message):
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True
    }
    async with aiohttp.ClientSession() as session:
        await session.post(url, json=payload)

