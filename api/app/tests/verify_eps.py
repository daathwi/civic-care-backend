import requests
import json
import sys

BASE_URL = "http://localhost:8000/api/v1"

def check_eps():
    print("Checking Escalation Priority Analytics...")
    
    # 1. Test the specialized endpoint
    try:
        res = requests.get(f"{BASE_URL}/analytics/grievances/escalation-priority")
        if res.status_code == 200:
            data = res.json()
            print(f"SUCCESS: Escalation priority endpoint returned {len(data)} items.")
            if data:
                print(f"Sample item EPS: {data[0].get('eps', {}).get('total')}")
                # Check sorting
                scores = [i['eps']['total'] for i in data]
                if scores == sorted(scores, reverse=True):
                    print("SUCCESS: Items are sorted by EPS descending.")
                else:
                    print("FAILURE: Items are NOT sorted by EPS descending.")
        else:
            print(f"FAILURE: Escalation priority endpoint returned {res.status_code}")
    except Exception as e:
        print(f"ERROR: {e}")

    # 2. Test the standard grievances endpoint for eps_score
    try:
        res = requests.get(f"{BASE_URL}/grievances?status=escalated")
        if res.status_code == 200:
            data = res.json()
            items = data.get('items', [])
            print(f"SUCCESS: Grievances list (escalated) returned {len(items)} items.")
            if items:
                has_eps = any(i.get('eps_score') is not None for i in items)
                if has_eps:
                    print(f"SUCCESS: At least one item has eps_score: {items[0].get('eps_score')}")
                else:
                    print("FAILURE: No items in standard list have eps_score populated.")
        else:
            print(f"FAILURE: Grievances list returned {res.status_code}")
    except Exception as e:
        print(f"ERROR: {e}")

if __name__ == "__main__":
    check_eps()
