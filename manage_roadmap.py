import pandas as pd
import os

FILE_PATH = "memory/financial_physics_roadmap_template.xlsx"

def add_email_fix_to_roadmap():
    if not os.path.exists(FILE_PATH):
        print(f"File not found: {FILE_PATH}")
        return

    try:
        df = pd.read_excel(FILE_PATH)
        print("Current Columns:", df.columns.tolist())
        print(f"Current rows: {len(df)}")
        
        # Check if task already exists
        target_task = "Fix Email HOLD/SELL Recommendations (Cache Invalidation)"
        mask = df["TASK"] == target_task
        
        new_row = {
            "TASK": target_task,
            "AREA": "Email Scanner",
            "DESCRIZIONE DETTAGLIATA": (
                "Bug critico: le raccomandazioni HOLD/SELL nell'email giornaliera erano basate su dati "
                "cached obsoleti (TICKER_CACHE). Questo causava 3 errori su 9 posizioni: "
                "RACE.MI e MUV2.DE mostravano HOLD invece di SELL (strategie chiuse l'11-12/02), "
                "MMM mostrava SELL invece di HOLD (strategia aperta dall'11/02). "
                "Secondo bug: ticker del portafoglio non presenti in tickers.js non venivano mai "
                "scansionati, risultando sempre in SELL."
            ),
            "STRATEGIA IMPLEMENTAZIONE IA": (
                "1) Creazione test standalone (test_email_standalone.py) con caricamento portfolio da Firebase. "
                "2) Analisi indipendente di tutti i 9 ticker del portafoglio per confermare le discrepanze. "
                "3) Invalidazione mirata della TICKER_CACHE per i soli ticker del portafoglio prima dello scan. "
                "4) Merge automatico dei ticker del portafoglio nella lista di scan."
            ),
            "FILE COINVOLTI": "backend/scanner.py, test_email_standalone.py",
            "STATO": "Done",
            "PRIORITÀ": "Critical",
            "BREAKING (SI/NO)": "NO",
            "INVARIANTS TOCCATI": "Data Consistency, Email Accuracy",
            "PIANO APPROVATO (SI/NO)": "SI",
            "TEST RICHIESTI": (
                "1) test_email_standalone.py - confronto raccomandazioni con email reale. "
                "2) Verifica post-deploy: email delle 16:30 deve riflettere stato reale delle strategie."
            ),
            "RISULTATO": (
                "Test standalone conferma: 4 HOLD (ITW, JNJ, TTE.PA, PANW), 2 SELL (RACE.MI, MUV2.DE). "
                "Tutte le discrepanze con l'email risolte."
            ),
            "NOTE": "Deploy ID: PENDING (15/02/2026)"
        }
        
        if mask.any():
            # Update existing row
            for col, val in new_row.items():
                if col in df.columns:
                    df.loc[mask, col] = val
            print(f"✅ Row updated: '{target_task}'")
        else:
            # Find next ID
            try:
                max_id = df["ID"].dropna().astype(int).max()
                new_id = max_id + 1
            except:
                new_id = len(df) + 1
            
            new_row["ID"] = new_id
            df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
            print(f"✅ New row added (ID={new_id}): '{target_task}'")
        
        # Show the updated/new row
        mask = df["TASK"] == target_task
        print("\nUpdated Row:")
        print(df.loc[mask].to_string())
        
        # Save
        df.to_excel(FILE_PATH, index=False)
        print(f"\n✅ Roadmap saved: {FILE_PATH}")
        
    except Exception as e:
        print(f"❌ Error updating roadmap: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    add_email_fix_to_roadmap()
