"""
Costruisce il SEME della storia dello stato del sistema usato dal sito:
backend/data/system_history.csv (data, X, numero di titoli), dal 2004.

Usa le stesse funzioni del sito (system_state.coherent_series), così il seme
e la coda aggiornata ogni giorno sono calcolati allo stesso modo. L'ultimo
giorno viene scartato se è la data di oggi: la barra potrebbe essere parziale.

    backend/venv/bin/python backend/research/build_system_history.py
    (FPR_LONG_PANEL=percorso.pkl con {"px": {ticker: Series di chiusure dal 2003}})
"""
import datetime

from common import pd
from second_law import load_long
import system_state as ss


def main():
    prices = load_long()
    co = ss.coherent_series(prices)
    today = pd.Timestamp(datetime.date.today())
    co = co[co.index < today]
    ss.write_history_csv(co, ss.SEED_PATH)
    an = ss.analyse(co)
    days = an.index[an["signal"]]
    clusters = []
    for d in days:
        if clusters and (an.index.get_loc(d) - an.index.get_loc(clusters[-1][1])) <= ss.HOLD:
            clusters[-1][1] = d
        else:
            clusters.append([d, d])
    print(f"seme scritto: {ss.SEED_PATH}")
    print(f"{len(co)} giorni dal {co.index[0].date()} al {co.index[-1].date()} | titoli per giorno {int(co['n'].min())}-{int(co['n'].max())}")
    print(f"giorni di segnale: {int(an['signal'].sum())} | episodi: {len(clusters)} | stato oggi: {ss.current_state(an)}")
    print("episodi (primo giorno di segnale): " + ", ".join(str(a.date()) for a, _ in clusters))


if __name__ == "__main__":
    main()
