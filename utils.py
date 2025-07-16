import os
import json
import base64
import aiohttp
import logging
import signal
import sys
from datetime import datetime, timezone
from solders.keypair import Keypair
from solders.transaction import VersionedTransaction
from solana.rpc.async_api import AsyncClient
from solana.rpc.types import TxOpts
import asyncio
import traceback

logging.basicConfig(level=logging.INFO)
logging.info("=== Bot started successfully ===")

MAX_TOKEN_AGE_SECONDS = 30 * 60  # Buy tokens that are between 0 and 30 minutes old
MIN_LIQUIDITY_LAMPORTS = 20 * 1_000_000_000  # 20 SOL

# --- ENVIRONMENT VARIABLES & VALIDATION ---
REQUIRED_ENVS = [
    "PRIVATE_KEY", "HELIUS_API_KEY", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"
]
for var in REQUIRED_ENVS:
    if not os.getenv(var):
        logging.error(f"Missing required environment variable: {var}")
        sys.exit(1)

try:
    PRIVATE_KEY = json.loads(os.getenv("PRIVATE_KEY"))
    keypair = Keypair.from_bytes(bytes(PRIVATE_KEY))
except Exception as e:
    logging.error(f"Invalid PRIVATE_KEY format: {e}")
    sys.exit(1)

HELIUS_API_KEY = os.getenv("HELIUS_API_KEY")
RPC_URL = os.getenv("RPC_URL", f"https://mainnet.helius-rpc.com/?api-key={HELIUS_API_KEY}")
BUY_AMOUNT_SOL = float(os.getenv("BUY_AMOUNT_SOL", 0.01))
SLIPPAGE = float(os.getenv("SLIPPAGE", 3))
PROFIT_TARGET = float(os.getenv("PROFIT_TARGET", 1.5))
STOP_LOSS = float(os.getenv("STOP_LOSS", 0.7))
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
HELIUS_URL = f"https://mainnet.helius-rpc.com/?api-key={HELIUS_API_KEY}"
PUMP_PROGRAM_ID = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
JUPITER_QUOTE_URL = "https://quote-api.jup.ag/v6/quote"
JUPITER_SWAP_URL = "https://quote-api.jup.ag/v6/swap"
WRAPPED_SOL = "So11111111111111111111111111111111111111112"
POSITIONS_FILE = "positions.json"

# --- POSITION PERSISTENCE ---
def load_positions():
    if os.path.exists(POSITIONS_FILE):
        try:
            with open(POSITIONS_FILE, "r") as f:
                return json.load(f)
        except Exception as e:
            logging.warning(f"Failed to load positions: {e}")
    return {}

def save_positions(positions):
    try:
        with open(POSITIONS_FILE, "w") as f:
            json.dump(positions, f)
    except Exception as e:
        logging.warning(f"Failed to save positions: {e}")

positions = load_positions()  # mint -> {buy_price, time}

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
        for attempt in range(3):
            try:
                async with session.post(url, json=payload, timeout=10) as resp:
                    if resp.status == 429:
                        retry_after = int((await resp.json()).get("parameters", {}).get("retry_after", 1))
                        logging.warning(f"[telegram] Rate limited, retrying in {retry_after}s")
                        await asyncio.sleep(retry_after)
                        continue
                    break
            except Exception as e:
                logging.error(f"[telegram] {e}")
                await asyncio.sleep(2)

# --- HELIUS & JUPITER HELPERS ---
async def get_recent_signatures(limit=10):
    payload = {
        "jsonrpc": "2.0", "id": 1, "method": "getSignaturesForAddress",
        "params": [PUMP_PROGRAM_ID, {"limit": limit}]
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(HELIUS_URL, json=payload, timeout=10) as resp:
                result = await resp.json()
                return [tx["signature"] for tx in result.get("result", [])]
    except Exception as e:
        logging.warning(f"[signatures] {e}")
        return []

async def get_token_mints_from_tx(signature):
    payload = {
        "jsonrpc": "2.0", "id": 1, "method": "getTransaction",
        "params": [signature, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}]
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(HELIUS_URL, json=payload, timeout=10) as resp:
                result = await resp.json()
                meta = result.get("result", {}).get("meta", {})
                mints = set()
                for bal in meta.get("preTokenBalances", []) + meta.get("postTokenBalances", []):
                    if "mint" in bal:
                        mints.add(bal["mint"])
                return list(mints)
    except Exception as e:
        logging.warning(f"[get_mints] {e}")
        return []

async def fetch_recent_tokens(limit=10):
    signatures = await get_recent_signatures(limit)
    all_mints = set()
    for sig in signatures:
        mints = await get_token_mints_from_tx(sig)
        all_mints.update(mints)
    return [{"mint": mint} for mint in all_mints if mint != WRAPPED_SOL]

async def get_token_creation_time(mint):
    payload = {
        "jsonrpc": "2.0", "id": 1, "method": "getAccountInfo",
        "params": [mint, {"encoding": "jsonParsed"}]
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(HELIUS_URL, json=payload, timeout=10) as resp:
                result = await resp.json()
                lamports = result.get("result", {}).get("value", {}).get("lamports")
                if lamports:
                    slot_time = result.get("result", {}).get("context", {}).get("slot")
                    return datetime.now(timezone.utc).timestamp()  # placeholder for now
    except Exception as e:
        logging.warning(f"[creation_time] {e}")
    return None

async def has_liquidity(mint):
    params = {
        "inputMint": WRAPPED_SOL,
        "outputMint": mint,
        "amount": str(int(BUY_AMOUNT_SOL * 1_000_000_000)),
        "slippageBps": int(SLIPPAGE * 100),
        "onlyDirectRoutes": "false"
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(JUPITER_QUOTE_URL, params=params, timeout=10) as resp:
                data = await resp.json()
                if resp.status != 200:
                    logging.warning(f"[has_liquidity] Error {resp.status}: {data}")
                    return False
                for route in data.get("data", []):
                    if route.get("outAmount") and int(route["outAmount"]) >= MIN_LIQUIDITY_LAMPORTS:
                        return True
                return False
    except Exception as e:
        logging.warning(f"[has_liquidity] {e}")
        return False

async def get_swap_route(input_mint, output_mint, amount):
    params = {
        "inputMint": input_mint,
        "outputMint": output_mint,
        "amount": str(amount),
        "slippageBps": int(SLIPPAGE * 100),
        "onlyDirectRoutes": "false"
    }
    async with aiohttp.ClientSession() as session:
        async with session.get(JUPITER_QUOTE_URL, params=params, timeout=10) as resp:
            data = await resp.json()
            return data.get("data", [None])[0]

async def get_swap_transaction(route, user_public_key):
    payload = {
        "route": route,
        "userPublicKey": user_public_key,
        "wrapUnwrapSOL": True,
        "asLegacyTransaction": False
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(JUPITER_SWAP_URL, json=payload, timeout=10) as resp:
            data = await resp.json()
            return data.get("swapTransaction")

async def execute_swap(swap_txn_b64, client):
    txn_bytes = base64.b64decode(swap_txn_b64)
    txn = VersionedTransaction.deserialize(txn_bytes)
    txn.sign([keypair])
    sig = await client.send_raw_transaction(txn.serialize(), opts=TxOpts(skip_preflight=True))
    await client.confirm_transaction(sig.value)
    return sig.value

async def execute_buy(mint, client):
    route = await get_swap_route(WRAPPED_SOL, mint, int(BUY_AMOUNT_SOL * 1_000_000_000))
    if not route:
        return False, None
    swap_txn_b64 = await get_swap_transaction(route, str(keypair.pubkey()))
    sig = await execute_swap(swap_txn_b64, client)
    price = float(route["outAmount"]) / float(route["inAmount"])
    positions[mint] = {"buy_price": price, "time": datetime.now(timezone.utc).timestamp()}
    save_positions(positions)
    await send_telegram_message(f"✅ Bought `{mint}`\nTx: https://solscan.io/tx/{sig}")
    return True, sig

async def check_for_sell(client):
    for mint, info in list(positions.items()):
        route = await get_swap_route(mint, WRAPPED_SOL, 1_000_000)
        if not route:
            continue
        price = float(route["outAmount"]) / float(route["inAmount"])
        pnl = price / info["buy_price"]
        if pnl >= PROFIT_TARGET or pnl <= STOP_LOSS:
            swap_txn_b64 = await get_swap_transaction(route, str(keypair.pubkey()))
            sig = await execute_swap(swap_txn_b64, client)
            await send_telegram_message(f"💰 Sold `{mint}` at {round(pnl,2)}x\nTx: https://solscan.io/tx/{sig}")
            del positions[mint]
            save_positions(positions)

# --- MAIN LOOP ---
async def main_loop():
    async with AsyncClient(RPC_URL) as client:
        while True:
            try:
                tokens = await fetch_recent_tokens(limit=10)
                logging.info(f"[main] Fetched {len(tokens)} tokens")
                for token in tokens:
                    mint = token.get("mint")
                    if not mint or mint == WRAPPED_SOL or mint in positions:
                        continue
                    logging.info(f"[check] {mint}")

                    creation_time = await get_token_creation_time(mint)
                    if creation_time:
                        age = datetime.now(timezone.utc).timestamp() - creation_time
                        age_minutes = age / 60
                        if age > MAX_TOKEN_AGE_SECONDS:
                            logging.info(f"[skip] {mint} too old ({int(age_minutes)} min)")
                            continue

                    if await has_liquidity(mint):
                        success, _ = await execute_buy(mint, client)
                        if success:
                            await asyncio.sleep(2)
                await check_for_sell(client)
                await asyncio.sleep(10)
            except Exception as e:
                logging.error(f"[loop] {e}\n{traceback.format_exc()}")
                await asyncio.sleep(5)

# --- GRACEFUL SHUTDOWN ---
def shutdown_handler(loop):
    logging.info("Shutting down gracefully...")
    save_positions(positions)
    loop.stop()

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda: shutdown_handler(loop))
    try:
        loop.run_until_complete(main_loop())
    finally:
        save_positions(positions)
        loop.close()
