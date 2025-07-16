import os
import json
import base64
import aiohttp
import logging
from datetime import datetime
from solders.keypair import Keypair
from solders.transaction import VersionedTransaction
from solana.rpc.async_api import AsyncClient
from solana.rpc.types import TxOpts
import asyncio
import traceback

logging.basicConfig(level=logging.INFO)
print("=== BOT.PY STARTED ===")

# --- ENVIRONMENT VARIABLES ---
RPC_URL = os.getenv("RPC_URL", "https://mainnet.helius-rpc.com/?api-key=" + os.getenv("HELIUS_API_KEY"))
PRIVATE_KEY = json.loads(os.getenv("PRIVATE_KEY"))
keypair = Keypair.from_bytes(bytes(PRIVATE_KEY))
BUY_AMOUNT_SOL = float(os.getenv("BUY_AMOUNT_SOL", 0.01))
SLIPPAGE = float(os.getenv("SLIPPAGE", 3))
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
HELIUS_API_KEY = os.getenv("HELIUS_API_KEY")
HELIUS_URL = f"https://mainnet.helius-rpc.com/?api-key={HELIUS_API_KEY}"
PUMP_PROGRAM_ID = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
JUPITER_QUOTE_URL = "https://quote-api.jup.ag/v6/quote"
JUPITER_SWAP_URL = "https://quote-api.jup.ag/v6/swap"
WRAPPED_SOL = "So11111111111111111111111111111111111111112"
PROFIT_TARGET = float(os.getenv("PROFIT_TARGET", 1.5))
STOP_LOSS = float(os.getenv("STOP_LOSS", 0.8))
PRICE_CHECK_INTERVAL = int(os.getenv("PRICE_CHECK_INTERVAL", 30))

last_liquidity_check = {}
held_tokens = {}

# --- GLOBAL JUPITER RATE LIMITER ---
JUPITER_RATE_LIMIT = 60  # requests per minute
jupiter_semaphore = asyncio.Semaphore(JUPITER_RATE_LIMIT)

async def jupiter_rate_limiter():
    async with jupiter_semaphore:
        await asyncio.sleep(60 / JUPITER_RATE_LIMIT)

# --- HELIUS TX FETCHING ---
async def get_recent_signatures(limit=10):
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "getSignaturesForAddress",
        "params": [PUMP_PROGRAM_ID, {"limit": limit}]
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(HELIUS_URL, json=payload, timeout=10) as resp:
                result = await resp.json()
                return [tx["signature"] for tx in result.get("result", [])]
    except Exception as e:
        logging.warning(f"[get_recent_signatures] Failed: {e}\n{traceback.format_exc()}")
        return []

async def get_token_mints_from_tx(signature):
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "getTransaction",
        "params": [signature, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}]
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(HELIUS_URL, json=payload, timeout=10) as resp:
                result = await resp.json()
                meta = result.get("result", {}).get("meta", {})
                tx = result.get("result", {}).get("transaction", {})
                mints = set()

                for bal in meta.get("preTokenBalances", []) + meta.get("postTokenBalances", []):
                    if "mint" in bal:
                        mints.add(bal["mint"])

                for instr in tx.get("message", {}).get("instructions", []):
                    if "parsed" in instr and "info" in instr["parsed"]:
                        if "mint" in instr["parsed"]["info"]:
                            mints.add(instr["parsed"]["info"]["mint"])

                for inner in meta.get("innerInstructions", []):
                    for instr in inner.get("instructions", []):
                        if "parsed" in instr and "info" in instr["parsed"]:
                            if "mint" in instr["parsed"]["info"]:
                                mints.add(instr["parsed"]["info"]["mint"])

                return list(mints)
    except Exception as e:
        logging.warning(f"[get_token_mints_from_tx] Failed for {signature}: {e}\n{traceback.format_exc()}")
        return []

async def fetch_recent_tokens(limit=10):
    signatures = await get_recent_signatures(limit)
    all_mints = set()
    for sig in signatures:
        mints = await get_token_mints_from_tx(sig)
        all_mints.update(mints)
    return [{"mint": mint} for mint in all_mints if mint != WRAPPED_SOL]

# --- JUPITER UTILITIES ---
async def throttle_liquidity_check(mint):
    now = datetime.utcnow().timestamp()
    if mint in last_liquidity_check and now - last_liquidity_check[mint] < 1.1:
        await asyncio.sleep(1.1)
    last_liquidity_check[mint] = now

async def has_liquidity(mint):
    await jupiter_rate_limiter()  # Global rate limiter
    await throttle_liquidity_check(mint)
    params = {
        "inputMint": WRAPPED_SOL,
        "outputMint": mint,
        "amount": str(int(BUY_AMOUNT_SOL * 1_000_000_000)),
        "slippageBps": int(SLIPPAGE * 100),
        "onlyDirectRoutes": "true"
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(JUPITER_QUOTE_URL, params=params, timeout=10) as resp:
                data = await resp.json()
                if resp.status != 200:
                    logging.warning(f"[has_liquidity] Error {resp.status}: {data}")
                    return False
                return bool(data.get("data"))
    except Exception as e:
        logging.warning(f"[has_liquidity] Failed for {mint}: {e}\n{traceback.format_exc()}")
        return False

async def get_swap_route(input_mint, output_mint, amount, slippage=3):
    await jupiter_rate_limiter()  # Global rate limiter
    params = {
        "inputMint": input_mint,
        "outputMint": output_mint,
        "amount": str(amount),
        "slippageBps": int(slippage * 100),
        "onlyDirectRoutes": "true"
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(JUPITER_QUOTE_URL, params=params, timeout=10) as resp:
                data = await resp.json()
                if resp.status != 200 or not data.get("data"):
                    raise Exception(f"Route fetch failed: {resp.status} {data}")
                return data["data"][0]
    except Exception as e:
        logging.error(f"[get_swap_route] {e}\n{traceback.format_exc()}")
        raise

async def get_swap_transaction(route, user_public_key):
    await jupiter_rate_limiter()  # Global rate limiter
    payload = {
        "route": route,
        "userPublicKey": user_public_key,
        "wrapUnwrapSOL": True,
        "asLegacyTransaction": False
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(JUPITER_SWAP_URL, json=payload, timeout=10) as resp:
                data = await resp.json()
                if resp.status != 200 or "swapTransaction" not in data:
                    raise Exception(f"Transaction build failed: {data}")
                return data["swapTransaction"]
    except Exception as e:
        logging.error(f"[get_swap_transaction] {e}\n{traceback.format_exc()}")
        raise

async def execute_swap(swap_txn_b64, client):
    try:
        txn_bytes = base64.b64decode(swap_txn_b64)
        txn = VersionedTransaction.deserialize(txn_bytes)
        txn.sign([keypair])
        sig = await client.send_raw_transaction(txn.serialize(), opts=TxOpts(skip_preflight=True))
        await client.confirm_transaction(sig.value)
        return sig.value
    except Exception as e:
        logging.error(f"[execute_swap] {e}\n{traceback.format_exc()}")
        raise

# --- BUY AND SELL EXECUTION ---
async def execute_buy(mint):
    input_mint = WRAPPED_SOL
    amount = int(BUY_AMOUNT_SOL * 1_000_000_000)
    try:
        async with AsyncClient(RPC_URL) as client:
            route = await get_swap_route(input_mint, mint, amount, SLIPPAGE)
            swap_txn_b64 = await get_swap_transaction(route, str(keypair.pubkey()))
            sig = await execute_swap(swap_txn_b64, client)
            held_tokens[mint] = {
                "buy_price": float(route["outAmount"]) / 10**route["outDecimals"]
            }
            return True, sig
    except Exception as e:
        await send_telegram_message(f"❌ Buy failed for {mint}: {e}")
        return False, None

async def execute_sell(mint):
    token = held_tokens[mint]
    try:
        async with AsyncClient(RPC_URL) as client:
            route = await get_swap_route(mint, WRAPPED_SOL, int(token["buy_price"] * 1_000_000_000), SLIPPAGE)
            swap_txn_b64 = await get_swap_transaction(route, str(keypair.pubkey()))
            sig = await execute_swap(swap_txn_b64, client)
            await send_telegram_message(f"✅ Sold {mint} for profit/loss. Tx: {sig}")
            del held_tokens[mint]
    except Exception as e:
        await send_telegram_message(f"❌ Sell failed for {mint}: {e}")

# --- TELEGRAM ---
async def send_telegram_message(message):
    if not TELEGRAM_TOKEN or not CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True
    }
    async with aiohttp.ClientSession() as session:
        try:
            await session.post(url, json=payload, timeout=10)
        except Exception as e:
            logging.error(f"[send_telegram_message] {e}\n{traceback.format_exc()}")

# --- FILTER ---
def is_token_eligible(token):
    mint = token.get("mint")
    if not mint or mint == WRAPPED_SOL:
        return False, "Invalid or native SOL mint"
    return True, ""

# --- MAIN LOOP ---
async def monitor_prices():
    while True:
        for mint in list(held_tokens):
            try:
                route = await get_swap_route(mint, WRAPPED_SOL, int(held_tokens[mint]["buy_price"] * 1_000_000_000))
                out_amount = float(route["outAmount"]) / 10**route["outDecimals"]
                pnl = out_amount / held_tokens[mint]["buy_price"]
                if pnl >= PROFIT_TARGET or pnl <= STOP_LOSS:
                    await execute_sell(mint)
            except Exception as e:
                logging.warning(f"[monitor_prices] Failed for {mint}: {e}")
        await asyncio.sleep(PRICE_CHECK_INTERVAL)

async def main():
    tokens = await fetch_recent_tokens(limit=10)
    for token in tokens:
        mint = token.get("mint")
        eligible, reason = is_token_eligible(token)
        if eligible and await has_liquidity(mint):
            success, sig = await execute_buy(mint)
            if success:
                await send_telegram_message(f"✅ Bought {mint}\nTx: {sig}")
        await asyncio.sleep(1)

async def main_loop():
    await asyncio.gather(
        monitor_prices(),
        *(main() for _ in range(1))  # adjustable for concurrent scans
    )

if __name__ == "__main__":
    asyncio.run(main_loop())
