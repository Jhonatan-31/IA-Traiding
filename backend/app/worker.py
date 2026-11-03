import asyncio
import psycopg
from .main import setup,work

async def main():
    while True:
        try:
            setup()
            break
        except psycopg.OperationalError:
            await asyncio.sleep(2)
    await work()

if __name__=='__main__':asyncio.run(main())
