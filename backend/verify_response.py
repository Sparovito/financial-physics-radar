
import requests
import json

url = "http://localhost:8000/analyze"
payload = {
    "ticker": "SPY",
    "alpha": 200,
    "beta": 1,
    "top_k": 5,
    "forecast_days": 60,
    "start_date": "2024-01-01",
    "use_cache": False
}

try:
    print("Calling API...")
    response = requests.post(url, json=payload)
    if response.status_code == 200:
        data = response.json()
        print("✅ Status 200")
        
        frozen = data.get("frozen_data", {})
        print(f"Frozen keys: {list(frozen.keys())}")
        
        z_slope = frozen.get("z_slope", [])
        z_sum = frozen.get("z_sum", [])
        
        print(f"z_slope length: {len(z_slope)}")
        print(f"z_sum length: {len(z_sum)}")
        
        if len(z_slope) > 0 and len(z_sum) > 0:
            print("✅ Data verified: z_slope and z_sum are present!")
        else:
            print("❌ Data missing: Lists are empty")
            
    else:
        print(f"❌ Error {response.status_code}: {response.text}")

except Exception as e:
    print(f"❌ Connection failed: {e}")
