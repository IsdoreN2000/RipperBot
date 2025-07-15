import asyncio
import logging
from telegram import handle_command
from solana.rpc.async_api import AsyncClient

logging.basicConfig(level=logging.INFO)

async def main():
    try:
        async with AsyncClient("https://api.mainnet-beta.solana.com") as client:
            await handle_command(client)
    except Exception as e:
        logging.error(f"Error in main: {e}")

if __name__ == "__main__":
    asyncio.run(main())
