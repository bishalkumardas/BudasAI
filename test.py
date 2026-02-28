import httpx
import certifi
import asyncio

async def test_resend():
    async with httpx.AsyncClient(verify=certifi.where(), timeout=10) as client:
        r = await client.get("https://api.resend.com/health")
        print(r.status_code, r.text)

asyncio.run(test_resend())