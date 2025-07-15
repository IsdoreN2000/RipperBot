import base64
import subprocess
import json
from typing import Any
from solders.pubkey import Pubkey
from solders.keypair import Keypair
from solana.rpc.async_api import AsyncClient
from solders.transaction import VersionedTransaction

async def create_buy_txn(
    client: AsyncClient,
    keypair: Keypair,
    mint: Pubkey,
    sol_amount: float,
    slippage: float
) -> VersionedTransaction:
    """
    Create a buy transaction for a given token mint using the pump-sdk bridge.
    Calls a Node.js script (pump_sdk_bridge.js) via subprocess.
    Returns a deserialized VersionedTransaction.
    """
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
        try:
            tx_data = json.loads(result.stdout)
            if "serialized_tx" not in tx_data:
                raise ValueError("No 'serialized_tx' in Node.js output")
            return VersionedTransaction.deserialize(base64.b64decode(tx_data["serialized_tx"]))
        except Exception as e:
            raise RuntimeError(f"Failed to parse Node.js output: {e}\nOutput: {result.stdout}")
    except subprocess.CalledProcessError as e:
        raise RuntimeError(
            f"Node.js script error: {e.stderr.strip()} | STDOUT: {e.stdout.strip()}"
        )
    except Exception as e:
        raise RuntimeError(f"Failed to create buy transaction: {e}")

async def create_sell_txn(
    client: AsyncClient,
    keypair: Keypair,
    mint: Pubkey,
    multiplier: float
) -> VersionedTransaction:
    """
    Create a sell transaction for a given token mint using the pump-sdk bridge.
    Calls a Node.js script (pump_sdk_bridge.js) via subprocess.
    Returns a deserialized VersionedTransaction.
    """
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
        try:
            tx_data = json.loads(result.stdout)
            if "serialized_tx" not in tx_data:
                raise ValueError("No 'serialized_tx' in Node.js output")
            return VersionedTransaction.deserialize(base64.b64decode(tx_data["serialized_tx"]))
        except Exception as e:
            raise RuntimeError(f"Failed to parse Node.js output: {e}\nOutput: {result.stdout}")
    except subprocess.CalledProcessError as e:
        raise RuntimeError(
            f"Node.js script error: {e.stderr.strip()} | STDOUT: {e.stdout.strip()}"
        )
    except Exception as e:
        raise RuntimeError(f"Failed to create sell transaction: {e}")
