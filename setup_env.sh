#!/bin/bash

# 1. Crea un ambiente virtuale chiamato 'venv'
echo "Creazione ambiente virtuale..."
python3 -m venv venv

# 2. Attiva l'ambiente
source venv/bin/activate

# 3. Aggiorna pip
echo "Aggiornamento pip..."
pip install --upgrade pip

# 4. Installa le librerie necessarie
echo "Installazione dipendenze (yfinance, plotly, pandas, scipy, ipykernel)..."
pip install yfinance pandas plotly scipy ipykernel

# 5. Registra questo ambiente come kernel per Jupyter
echo "Registrazione kernel Jupyter..."
python -m ipykernel install --user --name=financial_physics --display-name "Financial Physics"

echo "=============================================="
echo "Fatto! Ora segui questi passaggi:"
echo "1. Chiudi e riapri il tuo editor (VS Code o Jupyter)."
echo "2. Apri il file FinancialPhysicsTool.ipynb."
echo "3. Cerca l'opzione per cambiare Kernel (in alto a destra in VS Code)."
echo "4. Seleziona 'Financial Physics' dalla lista."
echo "=============================================="
