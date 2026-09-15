import asyncio
import os
import logging

import uvicorn

from bot import run_bot
from web import app

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("crypto-exchange")


async def monitored_bot():
    log.info("Starting Telegram bot in the same Render service...")
    try:
        await run_bot()
    except asyncio.CancelledError:
        log.info("Telegram bot task stopped.")
        raise
    except Exception:
        log.exception("Telegram bot stopped with an error.")


async def main():
    """Run web and Telegram in one service using the same database."""
    port = int(os.getenv("PORT", "8000"))
    config = uvicorn.Config(app, host="0.0.0.0", port=port, log_level="info")
    server = uvicorn.Server(config)
    bot_task = asyncio.create_task(monitored_bot())
    log.info("Starting web server on 0.0.0.0:%s", port)
    try:
        await server.serve()
    finally:
        bot_task.cancel()
        try:
            await bot_task
        except asyncio.CancelledError:
            pass


if __name__ == "__main__":
    asyncio.run(main())
