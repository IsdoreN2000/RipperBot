import base64
import subprocess
import json
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
    This function calls the unified Node.js script via subprocess.
    """
    try:
        result = subprocess.run(
            [
                "node",
                "pump_sdk_bridge.js",  # Unified Node.js bridge script
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
        # tx_data["serialized_tx"] is a base64-encoded transaction
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
    """
    Create a sell transaction for a given token mint using the pump-sdk bridge.
    This function calls the unified Node.js script via subprocess.
    """
    try:
        result = subprocess.run(
            [
                "node",
                "pump_sdk_bridge.js",  # Unified Node.js bridge script
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
