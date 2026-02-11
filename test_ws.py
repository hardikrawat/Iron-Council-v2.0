import asyncio
import websockets
import json

async def test_ws():
    uri = "ws://localhost:8000/ws/council"
    async with websockets.connect(uri) as websocket:
        print("Connected to WebSocket")
        
        # 1. Receive Init
        init_msg = await websocket.recv()
        print(f"Received: {json.loads(init_msg)['type']}")
        
        # 2. Receive Logs/History (flush them)
        try:
            while True:
                msg = await asyncio.wait_for(websocket.recv(), timeout=1.0)
                data = json.loads(msg)
                if data['type'] == 'system_log':
                    print(f"Values: {data['content']}")
                    continue
                if data['type'] == 'history':
                    continue
                print(f"Ignored: {data['type']}")
        except asyncio.TimeoutError:
            print("Finished flushing initial messages.")

        # 3. Send Message
        print("Sending 'Hello Council'")
        await websocket.send(json.dumps({"type": "chat", "content": "Hello Council"}))
        
        # 4. Wait for response or bridge event
        try:
            while True:
                msg = await asyncio.wait_for(websocket.recv(), timeout=30.0)
                data = json.loads(msg)
                print(f"Received: {data['type']}")
                if data['type'] == 'agent_post':
                    print(f"Verify Agent Response: {data['data']['name']} spoke!")
                    break
        except asyncio.TimeoutError:
            print("Timeout waiting for agent response.")

asyncio.run(test_ws())
