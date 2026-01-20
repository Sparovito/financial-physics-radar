import firebase_admin
from firebase_admin import credentials, firestore
import json
import os

def migrate():
    # 1. Setup paths
    base_dir = os.path.dirname(os.path.abspath(__file__))
    key_path = os.path.join(base_dir, "serviceAccountKey.json")
    local_file = os.path.join(base_dir, "portfolio.json")
    
    if not os.path.exists(key_path):
        print("❌ Errore: serviceAccountKey.json non trovato!")
        return

    if not os.path.exists(local_file):
        print("❌ Errore: portfolio.json locale non trovato!")
        return

    # 2. Init Firebase
    try:
        cred = credentials.Certificate(key_path)
        firebase_admin.initialize_app(cred)
        db = firestore.client()
        print("🔥 Firebase Connesso.")
    except Exception as e:
        print(f"❌ Errore connessione Firebase: {e}")
        return

    # 3. Load Local Data
    try:
        with open(local_file, "r") as f:
            data = json.load(f)
        positions = data.get("positions", [])
        print(f"📂 Dati locali caricati: {len(positions)} posizioni.")
    except Exception as e:
        print(f"❌ Errore lettura portfolio.json: {e}")
        return

    # 4. Upload to Firestore
    try:
        doc_ref = db.collection("portfolio").document("main")
        doc_ref.set(data)
        print("✅ Migrazione completata con successo!")
        print(f"   Caricate {len(positions)} posizioni su Firestore (Doc: portfolio/main).")
    except Exception as e:
        print(f"❌ Errore caricamento su Firebase: {e}")

if __name__ == "__main__":
    migrate()
