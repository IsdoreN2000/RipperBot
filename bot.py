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
from filelock import FileLock

logging.basicConfig(level=logging.INFO)
logging.info("=== Bot started successfully ===")

# --- Configurable Parameters ---
MIN_TOKEN_AGE_SECONDS = int(os.getenv("MIN_TOKEN_AGE_SECONDS", 0))
MAX_TOKEN_AGE_SECONDS = int(os.getenv("MAX_TOKEN_AGE_SECONDS", 3600))
MIN_LIQUIDITY_LAMPORTS = int(os.getenv("MIN_LIQUIDITY_LAMPORTS", 20 * 1_000_000_000))
POSITIONS_FILE = os.getenv("POSITIONS_FILE", "positions.json")
POSITIONS_LOCK_FILE = POSITIONS_FILE + ".lock"
JUPITER_MAX_RETRIES = int(os.getenv("JUPITER_MAX_RETRIES", 3))
JUPITER_BACKOFF_BASE = float(os.getenv("JUPITER_BACKOFF_BASE", 2.0))
JUPITER_BACKOFF_MAX = float(os.getenv("JUPITER_BACKOFF_MAX", 10.0))
SOLANA_COMMITMENT = os.getenv("SOLANA_COMMITMENT", "finalized")
SOLANA_CONFIRM_TIMEOUT = int(os.getenv("SOLANA_CONFIRM_TIMEOUT", 30))

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

PUMP_PROGRAM_IDS = [
    "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P",  # Pump.fun
    "BUNKU1mDhD6GNnpHJRZAZpEj3nGoqVZZe8RvAdTaLyoz"   # Bunk.fun
]

JUPITER_QUOTE_URL = "https://quote-api.jup.ag/v6/quote"
JUPITER_SWAP_URL = "https://quote-api.jup.ag/v6/swap"
WRAPPED_SOL = "So11111111111111111111111111111111111111112"

# --- Helper Functions ---

def get_current_utc_timestamp():
    return int(datetime.now(timezone.utc).timestamp())

def escape_markdown(text):
    # Escapes Telegram Markdown special characters
    for char in ('_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!'):
        text = text.replace(char, f'\\{char}')
    return text

def load_positions():
    if os.path.exists(POSITIONS_FILE):
        try:
            with FileLock(POSITIONS_LOCK_FILE, timeout=5):
                with open(POSITIONS_FILE, "r") as f:
                    return json.load(f)
        except Exception as e:
            logging.warning(f"Failed to load positions: {e}")
    return {}

def save_positions(positions):
    try:
        with FileLock(POSITIONS_LOCK_FILE, timeout=5):
            with open(POSITIONS_FILE, "w") as f:
                json.dump(positions, f)
    except Exception as e:
        logging.warning(f"Failed to save positions: {e}")

positions = load_positions()

async def send_telegram_message(message, session):
    if not TELEGRAM_TOKEN or not CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": escape_markdown(message),
        "parse_mode": "MarkdownV2",
        "disable_web_page_preview": True
    }
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

async def jupiter_get(session, url, params):
    for attempt in range(JUPITER_MAX_RETRIES):
        try:
            async with session.get(url, params=params, timeout=10) as resp:
                data = await resp.json()
                if resp.status == 429:
                    backoff = min(JUPITER_BACKOFF_BASE ** attempt, JUPITER_BACKOFF_MAX)
                    logging.warning(f"[jupiter] Rate limited, backoff {backoff}s")
                    await asyncio.sleep(backoff)
                    continue
                return data
        except Exception as e:
            backoff = min(JUPITER_BACKOFF_BASE ** attempt, JUPITER_BACKOFF_MAX)
            logging.warning(f"[jupiter] Error: {e}, backoff {backoff}s")
            await asyncio.sleep(backoff)
    return {}

async def get_recent_signatures(session, limit=10):
    all_signatures = []
    for program_id in PUMP_PROGRAM_IDS:
        payload = {
            "jsonrpc": "2.0", "id": 1, "method": "getSignaturesForAddress",
            "params": [program_id, {"limit": limit}]
        }
        try:
            async with session.post(HELIUS_URL, json=payload, timeout=10) as resp:
                result = await resp.json()
                sigs = [tx["signature"] for tx in result.get("result", [])]
                all_signatures.extend(sigs)
        except Exception as e:
            logging.warning(f"[signatures] {program_id}: {e}")
    return list(set(all_signatures))

async def get_token_mints_from_tx(session, signature):
    payload = {
        "jsonrpc": "2.0", "id": 1, "method": "getTransaction",
        "params": [signature, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}]
    }
    try:
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

async def fetch_recent_tokens(session, limit=10):
    signatures = await get_recent_signatures(session, limit)
    all_mints = set()
    for sig in signatures:
        mints = await get_token_mints_from_tx(session, sig)
        all_mints.update(mints)
    return [{"mint": mint} for mint in all_mints if mint != WRAPPED_SOL]

async def has_liquidity(session, mint):
    params = {
        "inputMint": WRAPPED_SOL,
        "outputMint": mint,
        "amount": str(int(BUY_AMOUNT_SOL * 1_000_000_000)),
        "slippageBps": int(SLIPPAGE * 100),
        "onlyDirectRoutes": "false"
    }
    data = await jupiter_get(session, JUPITER_QUOTE_URL, params)
    routes = data.get("data", [])
    if not routes:
        logging.info(f"[has_liquidity] {mint} no routes found")
        return False
    best_route = routes[0]
    out_amount = int(best_route.get("outAmount", 0))
    logging.info(f"[has_liquidity] {mint} out_amount: {out_amount}")
    return out_amount >= MIN_LIQUIDITY_LAMPORTS

async def get_token_creation_time(session, mint):
    payload = {
        "jsonrpc": "2.0", "id": 1, "method": "getAccountInfo",
        "params": [mint, {"encoding": "jsonParsed"}]
    }
    try:
        async with session.post(HELIUS_URL, json=payload, timeout=10) as resp:
            result = await resp.json()
            block_time = result.get("result", {}).get("value", {}).get("blockTime")
            if block_time:
                return block_time
    except Exception as e:
        logging.warning(f"[token_time] primary failed: {e}")

    payload = {
        "jsonrpc": "2.0", "id": 1, "method": "getSignaturesForAddress",
        "params": [mint, {"limit": 1}]
    }
    try:
        async with session.post(HELIUS_URL, json=payload, timeout=10) as resp:
            data = await resp.json()
            sigs = data.get("result", [])
            if sigs:
                slot = sigs[0].get("slot")
                if slot:
                    block_time_payload = {
                        "jsonrpc": "2.0", "id": 1, "method": "getBlockTime", "params": [slot]
                    }
                    async with session.post(HELIUS_URL, json=block_time_payload, timeout=10) as r:
                        block_data = await r.json()
                        return block_data.get("result")
    except Exception as e:
        logging.warning(f"[token_time fallback] {e}")

    return None

async def get_swap_route(session, input_mint, output_mint, amount):
    params = {
        "inputMint": input_mint,
        "outputMint": output_mint,
        "amount": str(amount),
        "slippageBps": int(SLIPPAGE * 100),
        "onlyDirectRoutes": "false"
    }
    data = await jupiter_get(session, JUPITER_QUOTE_URL, params)
    return data.get("data", [None])[0]

async def get_swap_transaction(session, route, user_public_key):
    payload = {
        "route": route,
        "userPublicKey": user_public_key,
        "wrapUnwrapSOL": True,
        "asLegacyTransaction": False
    }
    async with session.post(JUPITER_SWAP_URL, json=payload, timeout=10) as resp:
        data = await resp.json()
        return data.get("swapTransaction")

async def execute_swap(swap_txn_b64, client):
    txn_bytes = base64.b64decode(swap_txn_b64)
    txn = VersionedTransaction.deserialize(txn_bytes)
    txn.sign([keypair])
    sig = await client.send_raw_transaction(txn.serialize(), opts=TxOpts(skip_preflight=True))
    # Enhanced: Wait for confirmation with commitment and timeout
    try:
        await asyncio.wait_for(
            client.confirm_transaction(sig.value, commitment=SOLANA_COMMITMENT),
            timeout=SOLANA_CONFIRM_TIMEOUT
        )
    except asyncio.TimeoutError:
        logging.warning(f"[solana] Confirmation timeout for {sig.value}")
    return sig.value

async def execute_buy(session, mint, client):
    route = await get_swap_route(session, WRAPPED_SOL, mint, int(BUY_AMOUNT_SOL * 1_000_000_000))
    if not route:
        return False, None
    swap_txn_b64 = await get_swap_transaction(session, route, str(keypair.pubkey()))
    sig = await execute_swap(swap_txn_b64, client)
    price = float(route["outAmount"]) / float(route["inAmount"])
    positions[mint] = {"buy_price": price, "time": get_current_utc_timestamp()}
    save_positions(positions)
    await send_telegram_message(f"✅ Bought `{mint}`\nTx: https://solscan.io/tx/{sig}", session)
    return True, sig

async def check_for_sell(session, client):
    for mint, info in list(positions.items()):
        route = await get_swap_route(session, mint, WRAPPED_SOL, 1_000_000)
        if not route:
            continue
        price = float(route["outAmount"]) / float(route["inAmount"])
        pnl = price / info["buy_price"]
        if pnl >= PROFIT_TARGET or pnl <= STOP_LOSS:
            swap_txn_b64 = await get_swap_transaction(session, route, str(keypair.pubkey()))
            sig = await execute_swap(swap_txn_b64, client)
            await send_telegram_message(f"💰 Sold `{mint}` at {round(pnl, 2)}x\nTx: https://solscan.io/tx/{sig}", session)
            del positions[mint]
            save_positions(positions)

async def main_loop():
    async with aiohttp.ClientSession() as session:
        async with AsyncClient(RPC_URL) as client:
            while True:
                try:
                    tokens = await fetch_recent_tokens(session, limit=10)
                    logging.info(f"[main] Fetched {len(tokens)} tokens")
                    for token in tokens:
                        mint = token.get("mint")
                        if not mint or mint == WRAPPED_SOL or mint in positions:
                            continue
                        logging.info(f"[check] {mint}")
                        creation_time = await get_token_creation_time(session, mint)
                        if not creation_time:
                            logging.info(f"[skip] {mint} has no block_time")
                            continue
                        now = get_current_utc_timestamp()
                        age = now - creation_time
                        if not (MIN_TOKEN_AGE_SECONDS <= age <= MAX_TOKEN_AGE_SECONDS):
                            logging.info(f"[skip] {mint} age: {age}s")
                            continue
                        liquidity = await has_liquidity(session, mint)
                        if liquidity:
                            try:
                                success, _ = await execute_buy(session, mint, client)
                                if success:
                                    await asyncio.sleep(2)
                            except Exception as buy_exc:
                                logging.error(f"[buy] {mint} buy error: {buy_exc}")
                        else:
                            logging.info(f"[skip] {mint} insufficient liquidity")
                    await check_for_sell(session, client)
                    await asyncio.sleep(10)
                except Exception as e:
                    logging.error(f"[loop] {e}\n{traceback.format_exc()}")
                    await asyncio.sleep(5)

def shutdown_handler(loop):
    logging.info("Shutting down gracefully...")
    save_positions(positions)
    for task in asyncio.all_tasks(loop):
        task.cancel()
    loop.stop()

if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda: shutdown_handler(loop))
    try:
        loop.run_until_complete(main_loop())
    finally:
        save_positions(positions)
        loop.close()
