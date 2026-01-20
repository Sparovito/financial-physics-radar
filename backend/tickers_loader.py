import re
import json
import os

def load_tickers():
    path = os.path.join(os.path.dirname(__file__), "../frontend/tickers.js")
    if not os.path.exists(path):
        return []

    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    
    # Extract the object between { and the last };
    start = content.find("{")
    end = content.rfind("};") + 1
    if start == -1 or end == 0:
        return []
        
    js_obj = content[start:end]
    
    # Convert JS object syntax to JSON
    # 1. Quote unquoted keys:  symbol: "X" -> "symbol": "X"
    # We assume keys are alphanumeric. Top level keys are already quoted.
    # We look for " word:" pattern where 'word' is not quoted.
    # Actually, simplistic regex:  ([a-zA-Z0-9_]+):  -> "\1":
    # But check if already quoted?
    # In the file, inner keys are 'symbol:' and 'name:'. Top keys are '"Category":'. 
    # 'Category"' ends with quote. 'symbol' does not.
    # So we match (not quote) (word):
    
    # Attempting to regex replace unquoted keys
    # Lookbehind for non-quote? Python regex limit.
    # Easier: Just replace specific known keys 'symbol:' and 'name:' 
    js_obj = js_obj.replace(' symbol:', ' "symbol":')
    js_obj = js_obj.replace(' name:', ' "name":')
    
    # 2. Remove trailing commas
    js_obj = re.sub(r',\s*([\]}])', r'\1', js_obj)
    
    try:
        data = json.loads(js_obj)
        ticker_map = {}
        
        # Iterate to build map. Prioritize specific categories over 'Highlights'
        for category, items in data.items():
            for item in items:
                sym = item["symbol"]
                # If new, add. If existing is 'Highlights' and new is NOT, overwrite.
                if sym not in ticker_map:
                    ticker_map[sym] = category
                elif "Highlights" in ticker_map[sym] and "Highlights" not in category:
                    ticker_map[sym] = category
                    
        return ticker_map
    except Exception as e:
        print(f"Error parsing tickers.js: {e}")
        return {}
