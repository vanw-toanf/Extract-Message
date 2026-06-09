import asyncio, httpx
from dotenv import load_dotenv; load_dotenv()
import os, json

async def test():
    key = os.getenv('GOONG_API')
    address = 'thôn hạ, xã A Sào, tỉnh Hưng Yên'
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get('https://rsapi.goong.io/geocode', params={'address': address, 'api_key': key})
        print(json.dumps(r.json(), ensure_ascii=False, indent=2))

asyncio.run(test())