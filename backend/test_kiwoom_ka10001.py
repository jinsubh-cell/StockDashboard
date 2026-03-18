from services.kiwoom_provider import kiwoom
import json

def test_ka10001():
    print("Testing Kiwoom API ka10001...")
    data = kiwoom.get_current_price("005930")
    print("Samsung Price Data:")
    print(json.dumps(data, indent=4, ensure_ascii=False))

if __name__ == "__main__":
    test_ka10001()
