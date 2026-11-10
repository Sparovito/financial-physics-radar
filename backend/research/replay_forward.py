"""
RICOSTRUZIONE del forward test: rigioca giorno per giorno i dati reali da una
data di partenza a oggi, con lo stesso codice del journal (stessi segnali,
stessa regola t+1 / orizzonte fisso, stessi gruppi di confronto).

Serve a due cose:
- recuperare il periodo in cui il journal non era persistente (dal 2026-07-06,
  giorno in cui regole e parametri dell'ARANCIONE sono stati fissati: i dati
  successivi sono fuori campione rispetto al disegno della strategia);
- provare l'intera catena (scanner → journal → email) sull'universo completo.

NON è un registro dal vivo: è una ricostruzione, e resta in research/output/.
Non scrive nello storage operativo.

    backend/venv/bin/python backend/research/replay_forward.py [YYYY-MM-DD]
"""
import sys
import bisect
import datetime

from common import (os, json, np, fetch_prices, orange_inputs, save_output, OUTPUT_DIR)
from stable_strategy import backtest_potential_discharge, POTENTIAL_ALPHA, POTENTIAL_BETA
from forward_test import update_journal, journal_stats, journal_detail, BENCHMARK
from stable_scanner import build_orange_email

REPLAY_FROM = sys.argv[1] if len(sys.argv) > 1 else "2026-07-06"
ENTRY_Z, HORIZON = 2.0, 21


def main():
    from tickers_loader import load_tickers
    tickers = sorted(load_tickers().keys())
    if BENCHMARK not in tickers:
        tickers.append(BENCHMARK)
    start = (datetime.date.fromisoformat(REPLAY_FROM) - datetime.timedelta(days=760)).strftime("%Y-%m-%d")
    prices = fetch_prices(tickers, start, min_len=200, workers=8)
    print(f"universo {len(tickers)} -> scaricati {len(prices)} (dati dal {start})")

    series, events = {}, {}
    for t, px in prices.items():
        dates, pr, pot, F = orange_inputs(px)
        series[t] = (dates, pr)
        if len(pr) < 160:
            continue
        res = backtest_potential_discharge(dates, pr, pot, F, entry_z=ENTRY_Z, horizon=HORIZON,
                                           execution_lag=1, cost_pct=0.0)
        for ev in res["signal_events"]:
            if ev["type"] == "ENTRY" and ev["signal_date"] >= REPLAY_FROM:
                i = ev["signal_index"]
                depth = (F[i] - pr[i]) / F[i] * 100 if F[i] else 0.0
                events.setdefault(ev["signal_date"], []).append(
                    {"ticker": t, "signal_date": ev["signal_date"], "direction": "LONG",
                     "strategy": "ARANCIONE", "price": pr[i], "depth_pct": round(depth, 2),
                     "z": None})

    days = sorted({d for ds, _ in series.values() for d in ds if d >= REPLAY_FROM})
    params = {"strategy": "ARANCIONE", "entry_z": ENTRY_Z, "horizon": HORIZON,
              "potential_alpha": POTENTIAL_ALPHA, "potential_beta": POTENTIAL_BETA}
    journal = {"created": REPLAY_FROM, "config": {"note": "RICOSTRUZIONE, non registro dal vivo"}, "trades": []}
    universe = sorted(series)

    for day in days:
        sliced = {}
        for t, (ds, cs) in series.items():
            k = bisect.bisect_right(ds, day)
            if k:
                sliced[t] = (ds[:k], cs[:k])
        update_journal(journal, sliced, events.get(day, []), horizon=HORIZON,
                       params=params, universe=universe, run_date=day)

    stats = journal_stats(journal)
    save_output("replay_forward_journal.json", journal)

    last = days[-1]
    todays = events.get(last, [])
    result = {
        "entries_today": [{"ticker": e["ticker"], "price": e["price"], "current_price": e["price"],
                           "slope": 0.0, "depth_pct": e["depth_pct"], "price_change_since": 0.0,
                           "date": e["signal_date"], "direction": "LONG", "days_ago": 0,
                           "kind": "PANIC", "pending_execution": True} for e in todays],
        "entries_recent": [], "active": [], "errors": [],
        "params": {"alpha": 200, "mode": "LONG", "entry_threshold": 0, "exit_threshold": 0,
                   "strategy": "ARANCIONE", "entry_z": ENTRY_Z, "horizon": HORIZON,
                   "n_tickers": len(tickers), "n_downloaded": len(prices), "date": last},
        "forward_test": stats, "forward_detail": journal_detail(journal),
    }
    subject, body = build_orange_email(result)
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    html_path = os.path.join(OUTPUT_DIR, "email_preview.html")
    with open(html_path, "w") as f:
        f.write(body)

    sig_days = sorted(d for d in events if d <= last)
    per_day = [len(events[d]) for d in sig_days]
    print(f"\n=== RICOSTRUZIONE forward test {REPLAY_FROM} → {last} ({len(days)} giorni di scan) ===")
    print(f"segnali registrati: {stats['total']} in {len(sig_days)} giorni "
          f"(massimo in un giorno: {max(per_day) if per_day else 0})")
    print(f"chiusi {stats['closed']} | aperti {stats['open']} | settimane distinte {stats['n_clusters']}")
    print(f"titoli del segnale            : {stats['avg_pnl_pct']:+.2f}%/trade, win rate {stats['win_rate']}%   (atteso +3.4%, 65%)")
    print(f"titolo a caso, stesso giorno  : {stats['control_avg_pnl_pct']}%/trade su {stats['control_closed']}   (atteso +2.7%)")
    print(f"titolo a caso, giorno qualsiasi: {stats['baseline_avg_pnl_pct']}%/trade su {stats['baseline_closed']}   (atteso +1.2%)")
    print(f"indice nei giorni di panico   : {stats['index_avg_pnl_pct']}%/trade su {stats['index_closed']}")
    print(f"segnali − base {stats['edge_vs_baseline']} (t a cluster {stats['t_edge_baseline_clustered']}) | "
          f"dal giorno {stats['timing_edge']} | dal titolo {stats['edge_vs_control']} | contro SPY {stats['avg_excess_pct']}")
    print(f"t dei segnali contro zero: ingenuo {stats['t_naive']}, a cluster {stats['t_clustered']}")
    print(f"SEMAFORO: {stats['verdict']} — {stats['verdict_reason']}")
    print(f"\noggetto email: {subject}")
    print(f"anteprima email: {html_path}")


if __name__ == "__main__":
    main()
