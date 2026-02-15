import base64
import os

KEY_PATH = "backend/serviceAccountKey.json"

if not os.path.exists(KEY_PATH):
    print(f"❌ File not found: {KEY_PATH}")
    print("Please ensure your firebase key is in 'backend/serviceAccountKey.json'")
    exit(1)

with open(KEY_PATH, "rb") as f:
    json_bytes = f.read()
    encoded = base64.b64encode(json_bytes).decode('utf-8')

print("\n✅ COPIA QUESTA STRINGA SU RAILWAY:")
print("-" * 20)
print(encoded)
print("-" * 20)
print("\nVariable Name: FIREBASE_SERVICE_ACCOUNT_BASE64")
