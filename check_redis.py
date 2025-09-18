import asyncio
import redis.asyncio as redis

async def check_redis():
    r = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)
    
    # Get all position keys
    keys = await r.keys('position:*')
    print(f'Found {len(keys)} position keys: {keys}')
    
    for key in keys:
        data = await r.hgetall(key)
        print(f'\n{key}:')
        for field, value in data.items():
            print(f'  {field}: {value}')
    
    await r.close()

if __name__ == "__main__":
    asyncio.run(check_redis())
