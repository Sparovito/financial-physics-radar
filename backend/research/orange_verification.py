"""
Verifica della strategia ARANCIONE (scarico del potenziale) dal 2021.

Domande a cui risponde:
1. C'è un bias rialzista nascosto? (anno per anno — il 2022 orso è il test —
   correlazione col buy&hold, alpha aggiustato per esposizione)
2. Quanto è solida la significatività tenendo conto che i panici arrivano a
   grappolo? (t sulle medie settimanali + bootstrap a blocchi)
3. Money management: quota fissa vs tetto vs reinvestimento.

    backend/venv/bin/python backend/research/orange_verification.py
"""
from collections import defaultdict

from common import (np, sample_universe, fetch_prices, orange_inputs, cluster_stats,
                    simulate_sizing, save_output, tstat, COST)
from stable_strategy import backtest_potential_discharge

START = "2020-03-01"     # warmup: Kalman 100 barre + finestra z-score
FROM = "2021-01-01"
ENTRY_Z, HORIZON = 2.0, 21


def main():
    sample, n_univ = sample_universe()
    prices = fetch_prices(sample, START, min_len=600)
    print(f"universo {n_univ} -> campione {len(sample)} -> scaricati {len(prices)}")

    per_ticker, trades = [], []
    for t, px in prices.items():
        dates, pr, pot, F = orange_inputs(px)
        res = backtest_potential_discharge(dates, pr, pot, F, entry_z=ENTRY_Z,
                                           horizon=HORIZON, execution_lag=1,
                                           cost_pct=COST, start_date=FROM)
        st = res["stats"]
        i0 = next((i for i, d in enumerate(dates) if d >= FROM), 0)
        per_ticker.append({"ticker": t, "roi": st["total_return"], "expo": st["exposure_pct"],
                           "bh": (pr[-1] / pr[i0] - 1) * 100})
        trades += [(tr["entry_date"], tr["exit_date"], tr["pnl_pct"])
                   for tr in res["trades"] if tr["exit_date"] != "OPEN"]

    roi = np.array([r["roi"] for r in per_ticker])
    expo = np.array([r["expo"] for r in per_ticker])
    bh = np.array([r["bh"] for r in per_ticker])
    alpha = roi - expo / 100 * bh
    pnls = np.array([p for _, _, p in trades])

    out = {
        "params": {"entry_z": ENTRY_Z, "horizon": HORIZON, "from": FROM, "cost_pct_side": COST,
                   "n_tickers": len(per_ticker)},
        "per_ticker": {
            "mean_roi": round(float(roi.mean()), 2), "median_roi": round(float(np.median(roi)), 2),
            "mean_expo": round(float(expo.mean()), 1), "mean_bh": round(float(bh.mean()), 1),
            "alpha_expo_adj": round(float(alpha.mean()), 2),
            "t_alpha_cross_section": round(tstat(alpha), 2),
            "corr_roi_bh": round(float(np.corrcoef(bh, roi)[0, 1]), 3),
        },
        "per_trade": {
            "n": int(len(pnls)), "mean": round(float(pnls.mean()), 2),
            "median": round(float(np.median(pnls)), 2),
            "win_rate": round(float((pnls > 0).mean() * 100), 1),
            "worst": round(float(pnls.min()), 1), "best": round(float(pnls.max()), 1),
        },
        "clustered": cluster_stats([(en, p) for en, _, p in trades]),
    }

    by_year = defaultdict(list)
    for _, ex, p in trades:
        by_year[ex[:4]].append(p)
    out["by_year"] = {y: {"n": len(v), "sum": round(float(np.sum(v)), 1),
                          "mean": round(float(np.mean(v)), 2),
                          "win_rate": round(float((np.array(v) > 0).mean() * 100), 0)}
                      for y, v in sorted(by_year.items())}

    out["sizing"] = {
        "fixed_unlimited": simulate_sizing(trades, "fixed_unlimited"),
        "fixed_cap10": simulate_sizing(trades, "fixed", cap=10),
        "compound_cap10": simulate_sizing(trades, "compound", cap=10),
    }

    path = save_output("orange_verification.json", out)

    pt, tr, cl = out["per_ticker"], out["per_trade"], out["clustered"]
    print(f"\n=== ARANCIONE z>{ENTRY_Z} hold={HORIZON} dal {FROM} (costi {COST}%/lato) ===")
    print(f"per ticker : ROI medio {pt['mean_roi']}% (mediana {pt['median_roi']}%), expo {pt['mean_expo']}%, "
          f"B&H {pt['mean_bh']}%, alpha {pt['alpha_expo_adj']:+} (t cross-section {pt['t_alpha_cross_section']}), "
          f"corr con B&H {pt['corr_roi_bh']}")
    print(f"per trade  : n={tr['n']} media {tr['mean']:+}% mediana {tr['median']:+}% WR {tr['win_rate']}% "
          f"peggiore {tr['worst']}% migliore {tr['best']}%")
    print(f"SIGNIFICATIVITA': t ingenuo {cl['t_naive']} | t a cluster settimanali {cl['t_clustered']} "
          f"({cl['n_clusters']} settimane, la più grande pesa {cl['largest_cluster_share']*100:.0f}% dei trade)")
    print(f"                  bootstrap a blocchi: media/trade IC95 {cl['boot_ci95_mean_per_trade']}, "
          f"P(media<=0) = {cl['boot_p_mean_le_0']}")
    print("anno per anno:")
    for y, v in out["by_year"].items():
        print(f"  {y}: {v['n']:4d} trade | somma {v['sum']:+8.1f}% | media {v['mean']:+.2f}% | WR {v['win_rate']:.0f}%")
    print("sizing (capitale 100, quota 10%):")
    for k, v in out["sizing"].items():
        print(f"  {k:16s} ritorno {v['return_pct']:+.1f}%  maxDD {v['max_dd']}%  "
              f"max simultanee {v['max_concurrent']}  saltati {v['skipped']}")
    print(f"\nsalvato: {path}")


if __name__ == "__main__":
    main()
