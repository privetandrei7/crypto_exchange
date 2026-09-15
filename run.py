import asyncio
import threading

import uvicorn
from dotenv import load_dotenv

from bot import run_bot
from web import app

load_dotenv()

def run_web():
    uvicorn.run(app, host="127.0.0.1", port=8001, log_level="info")

async def main():
    t = threading.Thread(target=run_web, daemon=True)
    t.start()
    await run_bot()

if __name__ == "__main__":
    asyncio.run(main())
