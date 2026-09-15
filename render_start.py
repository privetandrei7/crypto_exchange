import asyncio
import os

import uvicorn

from bot import run_bot
from web import app


async def main():
    """Run the public web app and Telegram bot in ONE Render service.

    Both processes import the same application and therefore use the same
    DATABASE_URL / exchange.db. This prevents the web and bot from seeing
    different copies of orders.
    """
    port = int(os.getenv("PORT", "8000"))
    config = uvicorn.Config(
        app,
        host="0.0.0.0",
        port=port,
        log_level="info",
    )
    server = uvicorn.Server(config)
    bot_task = asyncio.create_task(run_bot())

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
