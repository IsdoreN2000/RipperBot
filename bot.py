import base64
import subprocess
import json
import time
from solders.pubkey import Pubkey
from solders.keypair import Keypair
from solana.rpc.async_api import AsyncClient
from solders.transaction import VersionedTransaction

# --- Pump.fun SDK Bridge Calls ---

async def create_buy_txn(
    client: AsyncClient,
    keypair: Keypair,
    mint: Pubkey,
    sol_amount: float,
    slippage: float
) -> VersionedTransaction:
    try:
        result = subprocess.run(
            [
                "node",
                "pump_sdk_bridge.js",
                "buy",
                str(mint),
                str(sol_amount),
                str(slippage),
                base64.b64encode(bytes(keypair)).decode("utf-8")
            ],
            capture_output=True,
            check=True,
            text=True
        )
        tx_data = json.loads(result.stdout)
        return VersionedTransaction.deserialize(base64.b64decode(tx_data["serialized_tx"]))
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"Node.js script error: {e.stderr.strip()}")
    except Exception as e:
        raise RuntimeError(f"Failed to create buy transaction: {e}")

async def create_sell_txn(
    client: AsyncClient,
    keypair: Keypair,
    mint: Pubkey,
    multiplier: float
) -> VersionedTransaction:
    try:
        result = subprocess.run(
            [
                "node",
                "pump_sdk_bridge.js",
                "sell",
                str(mint),
                str(multiplier),
                base64.b64encode(bytes(keypair)).decode("utf-8")
            ],
            capture_output=True,
            check=True,
            text=True
        )
        tx_data = json.loads(result.stdout)
        return VersionedTransaction.deserialize(base64.b64decode(tx_data["serialized_tx"]))
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"Node.js script error: {e.stderr.strip()}")
    except Exception as e:
        raise RuntimeError(f"Failed to create sell transaction: {e}")

def get_recent_tokens():
    try:
        result = subprocess.run(
            [
                "node",
                "pump_sdk_bridge.js",
                "recent"
            ],
            capture_output=True,
            check=True,
            text=True
        )
        data = json.loads(result.stdout)
        return data["tokens"]
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"Node.js script error: {e.stderr.strip()}")
    except Exception as e:
        raise RuntimeError(f"Failed to fetch recent tokens: {e}")

# --- Example: Monitor new launches and print them ---

def monitor_new_launches(poll_interval=10):
    seen = set()
    while True:
        tokens = get_recent_tokens()
        for token in tokens:
            mint = token.get("mint")
            if mint and mint not in seen:
                seen.add(mint)
                print("New launch detected:", token)
                # You can add auto-buy or notification logic here
        time.sleep(poll_interval)

# --- Example usage ---

if __name__ == "__main__":
    # To monitor new launches, simply run:
    monitor_new_launches()
    # For buy/sell, you would call create_buy_txn or create_sell_txn from your async workflow.
