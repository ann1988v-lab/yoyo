import asyncio, os
from dotenv import load_dotenv

load_dotenv()

import uvicorn
from bot import run_bot
from admin import app

async def web():
    cfg=uvicorn.Config(app,host=os.getenv("HOST","0.0.0.0"),port=int(os.getenv("PORT","8000")),log_level="info")
    await uvicorn.Server(cfg).serve()

async def main():
    await asyncio.gather(run_bot(), web())

if __name__=="__main__":
    asyncio.run(main())
