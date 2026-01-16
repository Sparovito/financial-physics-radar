import os
import sys
from pathlib import Path

def patch_yfinance_recursively():
    # Cerca la cartella site-packages
    # Parte dalla directory corrente e cerca nel venv
    venv_path = Path("backend/venv")
    if not venv_path.exists():
        print("❌ Venv non trovato in backend/venv")
        return

    # Trova site-packages (gestisce python3.9, python3.10, etc)
    site_packages = list(venv_path.glob("lib/python*/site-packages"))
    if not site_packages:
        print("❌ Cartella site-packages non trovata")
        return
    
    yfinance_dir = site_packages[0] / "yfinance"
    if not yfinance_dir.exists():
        print(f"❌ YFinance non trovato in {yfinance_dir}")
        return

    print(f"🔧 Scansione file in: {yfinance_dir} ...")
    
    count = 0
    # Scansiona tutti i file .py in yfinance
    for py_file in yfinance_dir.rglob("*.py"):
        try:
            with open(py_file, "r", encoding="utf-8") as f:
                content = f.read()
            
            # Se contiene il pipe '|' usato per i tipi (probabilmente) e non ha l'import future
            # O semplicemente per sicurezza, aggiungiamo future annotations a tutti i file che non ce l'hanno.
            if "from __future__ import annotations" not in content:
                # Aggiungi come PRIMA riga
                new_content = "from __future__ import annotations\n" + content
                
                with open(py_file, "w", encoding="utf-8") as f:
                    f.write(new_content)
                count += 1
                # print(f"  -> Patchato: {py_file.name}")
        except Exception as e:
            print(f"  ⚠️ Errore lettura {py_file.name}: {e}")

    print(f"✅ Applicata patch 'future annotations' a {count} file.")

if __name__ == "__main__":
    patch_yfinance_recursively()
