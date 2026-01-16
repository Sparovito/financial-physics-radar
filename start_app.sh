#!/bin/bash

# Ottieni la directory dove si trova lo script
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$DIR"

echo "=== Avvio Financial Physics Web App ==="
echo "----------------------------------------"

# 1. Setup Ambiente Virtuale (Python)
if [ ! -d "backend/venv" ]; then
    echo "Creating python environment with Python 3.11..."
    /opt/homebrew/bin/python3.11 -m venv backend/venv
fi

# ATTIVA SEMPRE l'ambiente
source backend/venv/bin/activate

# PULIZIA PREVENTIVA: Libera le porte 8000 e 3000
echo "🧹 Pulizia processi precedenti..."
lsof -ti:8000 | xargs kill -9 2>/dev/null
lsof -ti:3000 | xargs kill -9 2>/dev/null
sleep 1

# Aggiorna PIP
echo "Upgrading pip..."
pip install --upgrade pip

# INSTALLA SEMPRE le dipendenze (per aggiornamenti/fix)
echo "Checking dependencies..."
pip install --upgrade -r backend/requirements.txt

# Funzione per pulire i processi quando chiudi lo script
cleanup() {
    echo ""
    echo "🔴 Arresto sistemi..."
    if [ ! -z "$BACKEND_PID" ]; then kill $BACKEND_PID 2>/dev/null; fi
    if [ ! -z "$FRONTEND_PID" ]; then kill $FRONTEND_PID 2>/dev/null; fi
    exit
}
trap cleanup SIGINT

# 2. Avvia Backend (API) su porta 8000
echo "🚀 Avvio Backend Server (API)..."
cd backend
python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!
cd ..
echo "   -> API attiva su http://localhost:8000"
echo "   -> PID Backend: $BACKEND_PID"

# 3. Avvia Frontend (Sito Web)
# ORA GESTITO DAL BACKEND su 8000! 
# Non avviamo un server separato ma usiamo FastAPI per tutto.

echo "----------------------------------------"
echo "⏳ Attendo avvio servizi (5s)..."
sleep 5

# 4. Apri il browser
echo "🟢 Apertura Dashboard..."
# Su Mac 'open' apre il browser di default
open http://localhost:8000

echo "✅ TUTTO PRONTO!"
echo "Lascia questa finestra aperta."
echo "Premi CTRL+C per terminare."

# Attendi il processo backend
wait $BACKEND_PID
