import requests
import json

def test_ollama_connection():
    url = "http://localhost:11434/api/chat"
    payload = {
        "model": "qwen2.5:14b",
        "messages": [
            {"role": "system", "content": "You are a test script."},
            {"role": "user", "content": "Say 'Connection Successful'."}
        ],
        "stream": False
    }

    print(f"Targeting URL: {url}")
    print(f"Payload: {json.dumps(payload, indent=2)}")

    try:
        response = requests.post(url, json=payload, timeout=10)
        
        if response.status_code == 200:
            print("\n--- Status: 200 OK ---")
            print("Response Content:")
            print(json.dumps(response.json(), indent=2))
            
            # Helper to quickly see the message
            try:
                msg = response.json()['message']['content']
                print(f"\nResult: {msg}")
            except KeyError:
                print("\nWarning: Response was 200 but could not parse ['message']['content']")
        else:
            print(f"\n--- Status: {response.status_code} ---")
            print(f"Error Message: {response.text}")
            print(f"URL Attempted: {url}")

    except requests.exceptions.ConnectionError as e:
        print("\n--- Connection Error ---")
        print(f"Error Message: {e}")
        print(f"URL Attempted: {url}")
        print("\nTip: Make sure Ollama is running (ollama serve).")
    except Exception as e:
        print(f"\n--- Unexpected Error ---")
        print(f"Type: {type(e).__name__}")
        print(f"Message: {e}")

if __name__ == "__main__":
    test_ollama_connection()
