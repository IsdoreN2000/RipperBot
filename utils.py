...
# (Truncated previous unchanged parts)

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
                        if age > MAX_TOKEN_AGE_SECONDS:
                            logging.info(f"[skip] {mint} too old ({int(age)}s)")
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

# (Truncated rest of unchanged parts)
