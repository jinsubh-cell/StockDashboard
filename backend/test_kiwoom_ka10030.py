from services.kiwoom_provider import kiwoom
import json

def test_ka10030():
    print("Testing Kiwoom API ka10030...")
    data = kiwoom.get_top_volume_stocks()
    print("Response:")
    print(json.dumps(data, indent=4, ensure_ascii=False))

if __name__ == "__main__":
    test_ka10030()
