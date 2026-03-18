import requests
import json

def test_api():
    base_url = "http://localhost:8000"
    
    # Test Indices
    print("Testing Indices...")
    try:
        res = requests.get(f"{base_url}/api/market/indices", timeout=5)
        print(f"Indices status: {res.status_code}")
        print(f"Indices summary: {list(res.json().keys())}")
    except Exception as e:
        print(f"Indices failed: {e}")

    # Test Search
    print("\nTesting Search (Samsung)...")
    try:
        res = requests.get(f"{base_url}/api/market/search?q=삼성", timeout=10)
        print(f"Search status: {res.status_code}")
        data = res.json()
        print(f"Search results count: {len(data.get('results', []))}")
        if data.get('results'):
            print(f"First result: {data['results'][0]}")
    except Exception as e:
        print(f"Search failed: {e}")

if __name__ == "__main__":
    test_api()
