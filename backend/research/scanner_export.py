"""
Esporta e riassume il risultato dello SCANNER STRATEGIE (Massivo) su tutto
l'universo, con lo stesso calcolo dell'endpoint /scan-strategies.

Oltre al CSV per titolo, risponde a: "quanto vale lo scanner come strumento
per provare gli algoritmi?" — media contro mediana (peso dei titoli estremi),
quota di titoli che batte il compra-e-tieni, alpha, e soprattutto stabilità:
lo stesso scan su due metà del periodo dà la stessa classifica?

    backend/venv/bin/python backend/research/scanner_export.py [inizio] [fine]
"""
import sys
import csv

from common import (os, np, pd, save_output, OUTPUT_DIR, tstat)
from logic import MarketData
from strategy_scan import scan_one, fetch_prices_cached, aggregate_weekly, WARMUP_DAYS
import datetime
import pickle

START = sys.argv[1] if len(sys.argv) > 1 else "2023-01-01"
END = sys.argv[2] if len(sys.argv) > 2 else None
import system_state
SYSTEM_AN = system_state.analyse(system_state.read_history_csv(system_state.SEED_PATH))
STRATS = ["live", "frozen", "sum", "stable", "orange", "combo", "frozen2", "frozen2r", "system"]
LABEL = {"live": "Oracolo", "frozen": "Frozen", "sum": "SUM", "stable": "Stable",
         "orange": "Arancione", "combo": "Combo", "frozen2": "Frozen V2", "frozen2r": "V2 Risalita", "system": "Sistema"}


def spearman(a, b):
    return float(np.corrcoef(pd.Series(a).rank().values, pd.Series(b).rank().values)[0, 1])


def run(prices, start, end):
    out, errors = {}, {}
    for t, px in prices.items():
        try:
            out[t] = scan_one(px, start_date=start, end_date=end, system=SYSTEM_AN)
        except Exception as e:
            errors[t] = str(e)
    return out, errors


def weekly_table(res, title, split=None):
    """Significatività sul portafoglio a pesi uguali: eccesso settimanale medio tra i titoli,
    t sulle settimane (tiene conto del fatto che i titoli si muovono insieme)."""
    agg = aggregate_weekly({t: {"weekly": r["weekly"]} for t, r in res.items()})
    print(f"\n--- {title}: timing del portafoglio (tutti i titoli a pesi uguali) ---")
    print(f"{'strategia':10s} {'% / anno':>9s} {'t':>6s} {'t 1a metà':>10s} {'t 2a metà':>10s} {'settimane':>10s}")
    out = {}
    for s in STRATS:
        weeks = sorted(agg.get(s, {}))
        x = np.array([agg[s][k][0] / agg[s][k][1] for k in weeks])
        cut = len(x) // 2 if split is None else sum(1 for k in weeks if k < split)
        out[s] = {"per_year": float(x.mean() * 52 * 100), "t": tstat(x), "t_h1": tstat(x[:cut]), "t_h2": tstat(x[cut:]),
                  "weeks": len(x)}
        print(f"{LABEL[s]:10s} {out[s]['per_year']:+9.1f} {out[s]['t']:6.1f} {out[s]['t_h1']:10.1f} {out[s]['t_h2']:10.1f} {len(x):10d}")
    return out


def summary(res, title):
    bh = np.array([r["bh"] for r in res.values()])
    print(f"\n=== {title} — {len(res)} titoli | B&H medio {bh.mean():+.1f}%, mediano {np.median(bh):+.1f}% ===")
    print(f"{'strategia':10s} {'ROI medio':>10s} {'ROI mediano':>12s} {'alpha medio':>12s} {'alpha med.':>11s} "
          f"{'timing med.':>12s} {'timing mdn':>11s} {'batte B&H':>10s} {'espos.':>7s} {'win':>6s} {'trade':>6s}")
    rows = {}
    for s in STRATS:
        roi = np.array([r["strategies"][s]["roi"] for r in res.values()])
        al = np.array([r["strategies"][s]["alpha"] for r in res.values()])
        ex = np.array([r["strategies"][s]["expo"] for r in res.values()])
        wr = np.array([r["strategies"][s]["win_rate"] for r in res.values()])
        tr = np.array([r["strategies"][s]["trades"] for r in res.values()])
        tm = np.array([r["strategies"][s]["timing"] for r in res.values()])
        beat = float((roi > bh).mean() * 100)
        rows[s] = {"roi_mean": float(roi.mean()), "roi_median": float(np.median(roi)),
                   "alpha_mean": float(al.mean()), "alpha_median": float(np.median(al)),
                   "timing_mean": float(tm.mean()), "timing_median": float(np.median(tm)),
                   "timing_pos_share": float((tm > 0).mean() * 100),
                   "beat_bh": beat, "expo": float(ex.mean())}
        print(f"{LABEL[s]:10s} {roi.mean():+10.1f} {np.median(roi):+12.1f} {al.mean():+12.1f} {np.median(al):+11.1f} "
              f"{tm.mean():+12.1f} {np.median(tm):+11.1f} {beat:9.0f}% {ex.mean():6.0f}% {wr.mean():5.0f}% {tr.mean():6.1f}")
    return rows


def main():
    from tickers_loader import load_tickers
    cats = load_tickers()
    tickers = sorted(cats)
    warm = (datetime.date.fromisoformat(START) - datetime.timedelta(days=WARMUP_DAYS)).strftime("%Y-%m-%d")
    cache = os.environ.get("FPR_PANEL_CACHE")
    if cache and os.path.exists(cache):
        prices, failed = pickle.load(open(cache, "rb"))["px"], {}
    else:
        prices, failed = fetch_prices_cached(tickers, warm, lambda t, s: MarketData(t, start_date=s).fetch())
    print(f"universo {len(tickers)} | scaricati {len(prices)} | non scaricati {len(failed)}")

    full, err = run(prices, START, END)
    print(f"analizzati {len(full)} | scartati per storia insufficiente o errore {len(err)}")

    # ---------- CSV per titolo ----------
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    path = os.path.join(OUTPUT_DIR, "scanner_massivo.csv")
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        head = ["ticker", "categoria", "trend", "barre", "bh_pct"]
        for s in STRATS:
            head += [f"{s}_roi", f"{s}_alpha", f"{s}_timing", f"{s}_win", f"{s}_trade", f"{s}_expo"]
        w.writerow(head)
        for t in sorted(full):
            r = full[t]
            row = [t, cats.get(t, ""), r["trend"], r["n_bars"], r["bh"]]
            for s in STRATS:
                st = r["strategies"][s]
                row += [st["roi"], st["alpha"], st["timing"], st["win_rate"], st["trades"], st["expo"]]
            w.writerow(row)

    rows_full = summary(full, f"PERIODO INTERO {START} → {END or 'oggi'}")
    print("alpha = ROI − esposizione × B&H (lineare, distorto verso il basso sui titoli saliti molto); "
          "timing = eccesso sui rendimenti log giornalieri (zero in media con tempi a caso).")
    wk_full = weekly_table(full, "PERIODO INTERO")

    # ---------- peso dei titoli estremi ----------
    print("\n--- Quanto pesa una manciata di titoli sulla media del ROI ---")
    for s in ("live", "stable", "combo", "frozen2", "frozen2r", "system"):
        roi = sorted(((r["strategies"][s]["roi"], t) for t, r in full.items()), reverse=True)
        tot = sum(v for v, _ in roi)
        top = roi[:10]
        print(f"{LABEL[s]:10s} i 10 titoli migliori fanno il {sum(v for v, _ in top) / tot * 100:.0f}% della somma "
              f"({', '.join(t for _, t in top[:5])}…); senza di loro la media passa da "
              f"{tot / len(roi):+.1f}% a {(tot - sum(v for v, _ in top)) / (len(roi) - 10):+.1f}%")

    # ---------- per classe di attivo ----------
    def klass(t):
        if t.endswith("-USD"):
            return "Crypto"
        if t.endswith("=X"):
            return "Valute"
        if t.endswith("=F"):
            return "Materie prime"
        c = cats.get(t, "")
        if "ETF" in c.upper():
            return "ETF"
        return "Azioni"
    groups = {}
    for t, r in full.items():
        groups.setdefault(klass(t), []).append(r)
    print("\n--- Per classe di attivo: timing medio ---")
    print(f"{'classe':14s} {'n':>4s} {'B&H':>8s} " + " ".join(f"{LABEL[s]:>10s}" for s in STRATS))
    for g, rs in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        bhm = np.mean([r["bh"] for r in rs])
        print(f"{g:14s} {len(rs):4d} {bhm:+8.1f} " +
              " ".join(f"{np.mean([r['strategies'][s]['timing'] for r in rs]):+10.1f}" for s in STRATS))

    # ---------- stabilità: due metà del periodo ----------
    end_d = datetime.date.fromisoformat(END) if END else datetime.date.today()
    start_d = datetime.date.fromisoformat(START)
    mid = (start_d + (end_d - start_d) / 2).strftime("%Y-%m-%d")
    h1, _ = run(prices, START, mid)
    h2, _ = run(prices, mid, END)
    r1 = summary(h1, f"PRIMA METÀ {START} → {mid}")
    r2 = summary(h2, f"SECONDA METÀ {mid} → {END or 'oggi'}")
    common = sorted(set(h1) & set(h2))
    print(f"\n--- Stabilità tra le due metà ({len(common)} titoli in comune) ---")
    print(f"{'strategia':10s} {'timing 1a metà':>14s} {'timing 2a metà':>14s} {'stesso titolo: legame tra le due metà':>40s}")
    for s in STRATS:
        a1 = [h1[t]["strategies"][s]["timing"] for t in common]
        a2 = [h2[t]["strategies"][s]["timing"] for t in common]
        print(f"{LABEL[s]:10s} {r1[s]['timing_mean']:+14.1f} {r2[s]['timing_mean']:+14.1f} {spearman(a1, a2):+40.2f}")
    order1 = sorted((s for s in STRATS if s != "live"), key=lambda s: -r1[s]["timing_mean"])
    order2 = sorted((s for s in STRATS if s != "live"), key=lambda s: -r2[s]["timing_mean"])
    print("classifica per timing, 1a metà:", " > ".join(LABEL[s] for s in order1))
    print("classifica per timing, 2a metà:", " > ".join(LABEL[s] for s in order2))

    save_output("scanner_massivo_summary.json", {"start": START, "end": END, "mid": mid,
                                                 "full": rows_full, "h1": r1, "h2": r2, "weekly": wk_full,
                                                 "n": len(full), "failed": len(failed), "errors": len(err)})
    print(f"\nCSV per titolo: {path}")


if __name__ == "__main__":
    main()
