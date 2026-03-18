import asyncio
import logging
from services.kiwoom_ws import kiwoom_ws_manager

logging.basicConfig(level=logging.DEBUG)

async def test_ws():
    # Start the manager
    asyncio.create_task(kiwoom_ws_manager.run())
    
    # Wait for login
    print("Waiting 3s for login...")
    await asyncio.sleep(3)
    
    # Subscribe to Samsung Electronics
    print("Subscribing to 005930...")
    await kiwoom_ws_manager.subscribe_stocks(["005930", "000660"])
    
    # Let it run for 10 seconds to collect real-time data
    print("Listening for 10 seconds...")
    for _ in range(10):
        print(f"Current dict state: {kiwoom_ws_manager.realtime_data}")
        await asyncio.sleep(1)
        
    await kiwoom_ws_manager.disconnect()

if __name__ == "__main__":
    asyncio.run(test_ws())
