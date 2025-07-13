import base64
import subprocess
import json
from solders.pubkey import Pubkey
from solders.keypair import Keypair
from solana.rpc.async_api import AsyncClient
from solders.transaction import VersionedTransaction

# If you have a direct Python binding for pump-swap-sdk, import and use it here.
# Otherwise, this template uses subprocess to call a Node.js script.

async def create_buy_txn(
    client: AsyncClient,
    keypair: Keypair,
    mint: Pubkey,
    sol_amount: float,
    slippage: float
) -> VersionedTransaction:
    """
    Create a buy transaction for a given token mint using the pump-swap-sdk.
    This template calls a Node.js script via subprocess. Replace with direct SDK calls if available.
    """
    # Example: Call a Node.js script and get the serialized transaction
    try:
        result = subprocess.run(
            [
                "node",
                "pump_buy.js",  # Your Node.js script
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
        # Assume tx_data["serialized_tx"] is a base64-encoded transaction
        return VersionedTransaction.deserialize(base64.b64decode(tx_data["serialized_tx"]))
    except Exception as e:
        raise RuntimeError(f"Failed to create buy transaction: {e}")

async def create_sell_txn(
    client: AsyncClient,
    keypair: Keypair,
    mint: Pubkey,
    multiplier: float
) -> VersionedTransaction:
    """
    Create a sell transaction for a given token mint using the pump-swap-sdk.
    This template calls a Node.js script via subprocess. Replace with direct SDK calls if available.
    """
    try:
        result = subprocess.run(
            [
                "node",
                "pump_sell.js",  # Your Node.js script
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
    except Exception as e:
        raise RuntimeError(f"Failed to create sell transaction: {e}")

