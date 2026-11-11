"""
Test degli STATI dell'arancione e della strategia "V2 Risalita".

Perché esistono (research/frozen_vs_energy.py, research/v2_bottoms.py): il
potenziale Frozen (arancione) è la cinetica dell'oracolo vista 9 barre dopo.
In basso (prezzo sotto il percorso, energia alta) c'è un vantaggio; la V2 però
esce quando l'energia rientra, cioè proprio mentre il prezzo si riavvicina al
percorso, e prende solo il 10% della risalita successiva.

Stati per barra (frozen_v2_states):
    0  energia nella media (o dati mancanti)
    1  prezzo SOTTO il percorso, energia alta, in carica   (energia in aumento)
    2  prezzo SOTTO il percorso, energia alta, in scarica
    3  prezzo SOPRA il percorso, energia alta, in carica
    4  prezzo SOPRA il percorso, energia alta, in scarica  (massimo arancione passato)

V2 Risalita (frozen_v2_rise_positions): entra con la V2 (stati 1-2), resta
dentro mentre il prezzo risale, esce quando
    - sopra il percorso l'energia è alta e comincia a scendere (stato 4), oppure
    - il prezzo, dopo essere salito sopra il percorso, torna sotto.

Esecuzione: backend/venv/bin/python backend/tests/test_frozen_v2_rise.py
"""
import os
import sys
import math

os.environ.setdefault("FPR_STORAGE", "local")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import numpy as np
import pandas as pd


def _dates(n):
    return pd.date_range("2022-01-03", periods=n, freq="B").strftime("%Y-%m-%d").tolist()


def _base(m=400):
    # energia di fondo in lievissimo calo: sempre sotto la propria media mobile → z < 0
    return [1.0 - 1e-6 * i for i in range(m)], [0.5] * m


def _px(n=900, seed=5):
    rng = np.random.default_rng(seed)
    rets = rng.normal(0.0004, 0.014, n)
    rets[600:604] = -0.05
    idx = pd.date_range("2022-01-03", periods=n, freq="B")
    return pd.Series(100 * np.exp(np.cumsum(rets)), index=idx)


def main():
    from stable_strategy import (frozen_v2_positions, frozen_v2_states, frozen_v2_rise_positions,
                                 backtest_frozen_v2, backtest_frozen_v2_rise)
    from strategy_scan import scan_one, v2_inputs, v2_chart_block, position_series

    # --- 1. scenario A: panico → risalita → massimo dell'arancione sopra il percorso ---
    pot, disp = _base()
    for k, v in enumerate([5, 6, 7, 8, 9, 10, 11, 12, 13, 14]):      # 300-309: sotto, energia in aumento
        pot[300 + k], disp[300 + k] = float(v), -3.0
    for k, v in enumerate([12, 10, 8, 6, 4]):                         # 310-314: sotto, energia alta ma in calo
        pot[310 + k], disp[310 + k] = float(v), -2.0
    for i in range(315, 325):                                         # 315-324: energia rientrata, ancora sotto
        disp[i] = -0.5
    for i in range(325, 335):                                         # 325-334: prezzo sopra il percorso
        disp[i] = 1.0
    for k, v in enumerate([6, 8, 10, 12, 14]):                        # 335-339: sopra, energia in aumento
        pot[335 + k], disp[335 + k] = float(v), 3.0
    for k, v in enumerate([13, 11, 10, 9, 9]):                        # 340-344: sopra, energia alta in calo
        pot[340 + k], disp[340 + k] = float(v), 3.0

    st = frozen_v2_states(pot, disp)
    assert len(st) == len(pot)
    assert st[:300] == [0] * 300, "energia nella media → stato 0"
    assert st[300:310] == [1] * 10, f"sotto + in carica → 1, è {st[300:310]}"
    assert st[310:315] == [2] * 5, f"sotto + in scarica → 2, è {st[310:315]}"
    assert st[315:335] == [0] * 20, "energia rientrata → 0"
    assert st[335:340] == [3] * 5, f"sopra + in carica → 3, è {st[335:340]}"
    assert st[340] == 3, "13 è ancora sopra il valore di 3 barre prima (10): in carica"
    assert st[341:345] == [4] * 4, f"sopra + in scarica → 4, è {st[341:345]}"

    # la V2 storica coincide con gli stati 1 e 2
    assert frozen_v2_positions(pot, disp) == [1 if s in (1, 2) else 0 for s in st]

    pos = frozen_v2_rise_positions(pot, disp)
    assert pos[:300] == [0] * 300
    assert pos[300:341] == [1] * 41, "entra col panico e resta dentro per tutta la risalita"
    assert pos[341:] == [0] * (len(pot) - 341), "esce al massimo dell'arancione sopra il percorso e non rientra"
    v2 = frozen_v2_positions(pot, disp)
    assert sum(v2[315:341]) == 0 and sum(pos[315:341]) == 26, "la V2 esce quando l'energia rientra; la Risalita resta"

    # --- 2. scenario B: risalita senza picco di energia → esce quando il prezzo torna sotto ---
    pot, disp = _base()
    for k in range(10):
        pot[300 + k], disp[300 + k] = 5.0 + k, -3.0
    for i in range(310, 320):
        disp[i] = -0.5
    for i in range(320, 330):
        disp[i] = 1.0
    for i in range(330, 400):
        disp[i] = -1.0
    pos = frozen_v2_rise_positions(pot, disp)
    assert pos[300:330] == [1] * 30 and pos[330:] == [0] * 70, "esce quando, dopo essere salito sopra, torna sotto"

    # --- 3. rientro: dopo l'uscita serve una nuova V2 ---
    for k in range(5):
        pot[360 + k], disp[360 + k] = 9.0 + k, -4.0
    pos = frozen_v2_rise_positions(pot, disp)
    assert pos[330:360] == [0] * 30 and pos[360:365] == [1] * 5

    # --- 4. dati mancanti: nessuna posizione, nessuno stato ---
    nan = [float("nan")] * 60
    assert frozen_v2_rise_positions(nan, nan) == [0] * 60
    assert frozen_v2_states(nan, nan) == [0] * 60

    # --- 5. causale: troncare i dati non cambia il passato ---
    pot, disp = _base()
    for k in range(10):
        pot[300 + k], disp[300 + k] = 5.0 + k, -3.0
    for i in range(310, 400):
        disp[i] = 1.0 if i >= 320 else -0.5
    full_p, full_s = frozen_v2_rise_positions(pot, disp), frozen_v2_states(pot, disp)
    for cut in (305, 322, 380):
        assert frozen_v2_rise_positions(pot[:cut], disp[:cut]) == full_p[:cut]
        assert frozen_v2_states(pot[:cut], disp[:cut]) == full_s[:cut]

    # --- 6. esecuzione t+1 col motore unificato ---
    pot, disp = _base()
    for k, v in enumerate([5, 6, 7, 8, 9, 10, 11, 12, 13, 14]):
        pot[300 + k], disp[300 + k] = float(v), -3.0
    for i in range(310, 335):
        disp[i] = -0.5 if i < 325 else 1.0
    for k, v in enumerate([6, 8, 10, 12, 14, 13, 11, 10, 9, 9]):
        pot[335 + k], disp[335 + k] = float(v), 3.0
    dts = _dates(400)
    prs = [100 + 0.1 * i for i in range(400)]
    res = backtest_frozen_v2_rise(dts, prs, pot, disp)
    tr = res["trades"][0]
    assert tr["entry_date"] == dts[301], "ingresso alla chiusura successiva al segnale"
    assert tr["exit_date"] == dts[342], f"uscita alla chiusura successiva al segnale di uscita, è {tr['exit_date']}"
    assert len(res["trade_pnl_curve"]) == len(dts)

    # --- 7. ingressi condivisi: v2_inputs dà le stesse serie usate dallo scanner ---
    px = _px()
    start, end = px.index[400].strftime("%Y-%m-%d"), px.index[800].strftime("%Y-%m-%d")
    d_all = px[px.index <= pd.Timestamp(end)]
    dts = d_all.index.strftime("%Y-%m-%d").tolist()
    prs = [float(v) for v in d_all.values]
    p_in, d_in = v2_inputs(d_all)
    assert len(p_in) == len(d_in) == len(prs)
    assert all(math.isnan(v) for v in p_in[:100]) and all(math.isnan(v) for v in d_in[:100])
    r = scan_one(px, start_date=start, end_date=end)
    direct = backtest_frozen_v2(dts, prs, p_in, d_in, start_date=start, end_date=end)
    assert abs(direct["stats"]["total_return"] - r["strategies"]["frozen2"]["roi"]) < 0.01

    # --- 8. scanner: la nuova colonna esiste, ha il timing, non vede il futuro ---
    assert "frozen2r" in r["strategies"], "manca la strategia V2 Risalita nello scanner"
    s2r = r["strategies"]["frozen2r"]
    assert math.isfinite(s2r["timing"]) and "frozen2r" in r["weekly"] and "frozen2r" in r["trades"]
    assert s2r["expo"] >= r["strategies"]["frozen2"]["expo"], "la Risalita tiene più a lungo della V2"
    lo = next(i for i, d in enumerate(dts) if d >= start)
    hi = len(dts) - 1
    ps = position_series(r["trades"]["frozen2r"], dts, lo, hi)
    logret = sum(math.log(prs[i] / prs[i - 1]) for i in range(lo + 1, hi + 1) if ps[i] > 0)
    assert abs(math.expm1(logret) * 100 - s2r["roi"]) < 0.05, "posizioni ricostruite ≠ ROI"
    r_trunc = scan_one(px.iloc[:801], start_date=start, end_date=None)
    b = r_trunc["strategies"]["frozen2r"]
    assert abs(s2r["roi"] - b["roi"]) < 1e-6 and s2r["trades"] == b["trades"] and abs(s2r["timing"] - b["timing"]) < 1e-6

    # --- 9. blocco per il grafico: stati allineati alle date + le due strategie ---
    blk = v2_chart_block(d_all, start_date=start, end_date=end)
    assert len(blk["state"]) == len(dts), "uno stato per barra, allineato alle date del grafico"
    assert set(blk["state"]) <= {0, 1, 2, 3, 4}
    assert blk["state"] == frozen_v2_states(p_in, d_in)
    for key in ("v2", "rise"):
        assert len(blk[key]["trade_pnl_curve"]) == len(dts) and "stats" in blk[key] and "trades" in blk[key]
    assert abs(blk["v2"]["stats"]["total_return"] - r["strategies"]["frozen2"]["roi"]) < 0.01
    assert abs(blk["rise"]["stats"]["total_return"] - s2r["roi"]) < 0.01
    # troncando la storia gli stati passati non cambiano (nessun ridisegno)
    blk_cut = v2_chart_block(d_all.iloc[:700], start_date=start, end_date=None)
    assert blk_cut["state"] == blk["state"][:700]

    # --- 10. pannello DIREZIONE: blu (oracolo) e arancione con il segno, nella stessa scala ---
    from stable_strategy import ORANGE_LAG_BARS, signed_energy
    assert ORANGE_LAG_BARS == 9, "ritardo misurato dell'arancione sul blu (research/frozen_vs_energy.py)"
    assert signed_energy([4.0, 9.0, float("nan"), 1.0], [-2.0, 3.0, 1.0, float("nan")], scale=2.0) == [-8.0, 18.0, None, None]
    dr = blk["direction"]
    assert dr["lag"] == ORANGE_LAG_BARS
    assert len(dr["orange"]) == len(dr["oracle"]) == len(dts), "una barra per data del grafico"
    assert 1.0 < dr["scale"] < 1.15, f"fattore di scala atteso ≈ 1.07, è {dr['scale']}"
    assert dr["orange"][:100] == [None] * 100, "riscaldamento del filtro: nessun valore"
    for i, stt in enumerate(blk["state"]):
        if stt in (1, 2):
            assert dr["orange"][i] < 0, "prezzo sotto il percorso → arancione negativo"
        elif stt in (3, 4):
            assert dr["orange"][i] > 0, "prezzo sopra il percorso → arancione positivo"
    k = next(i for i in range(300, len(dts)) if p_in[i] > 1e-3)
    assert abs(abs(dr["orange"][k]) - p_in[k] * dr["scale"]) < 1e-2 * max(1.0, p_in[k]), "|arancione| = potenziale × scala"
    # l'arancione è causale (il passato non cambia); il blu no: è l'oracolo, viene ridisegnato
    assert blk_cut["direction"]["orange"] == dr["orange"][:700]
    assert blk_cut["direction"]["oracle"] != dr["oracle"][:700], "il blu deve cambiare quando arrivano nuovi dati"
    # su una salita a ritmo costante le due curve coincidono (stessa scala) e sono positive
    ramp = pd.Series([100 + 0.5 * i for i in range(600)], index=pd.date_range("2022-01-03", periods=600, freq="B"))
    rb = v2_chart_block(ramp)["direction"]
    assert rb["oracle"][300] > 0 and rb["orange"][300] > 0
    assert abs(rb["oracle"][300] - rb["orange"][300]) / rb["oracle"][300] < 0.02, (rb["oracle"][300], rb["orange"][300])
    fall = pd.Series([400 - 0.5 * i for i in range(600)], index=ramp.index)
    fb = v2_chart_block(fall)["direction"]
    assert fb["oracle"][300] < 0 and fb["orange"][300] < 0, "in discesa entrambe sotto lo zero"

    # --- 10b. STIMA DI OGGI del blu (nowcast): sovrapposta senza spostamento, causale ---
    from strategy_scan import oracle_nowcast
    now = dr["nowcast"]
    assert len(now) == len(dts) and now[:100] == [None] * 100
    assert blk_cut["direction"]["nowcast"] == now[:700], "la stima di oggi non viene mai ridisegnata"
    assert abs(rb["nowcast"][300] - rb["oracle"][300]) / rb["oracle"][300] < 0.03, (rb["nowcast"][300], rb["oracle"][300])
    assert fb["nowcast"][300] < 0, "in discesa la stima è sotto lo zero"
    o_arr = np.array(dr["oracle"][300:], dtype=float)
    n_arr = np.array(now[300:], dtype=float)
    a_arr = np.array(dr["orange"][300:], dtype=float)
    c_now, c_old = np.corrcoef(n_arr, o_arr)[0, 1], np.corrcoef(a_arr, o_arr)[0, 1]
    assert c_now > c_old, f"nello stesso giorno la stima di oggi deve somigliare al blu più dell'arancione ({c_now:.2f} vs {c_old:.2f})"
    v_now = oracle_nowcast(d_all)
    assert len(v_now) == len(dts) and all(math.isnan(v) for v in v_now[:100]) and math.isfinite(v_now[300])
    assert all((v > 0) == (x > 0) for v, x in zip(v_now[300:], now[300:]) if x != 0), "stesso segno di velocità ed energia"

    # --- 10c. le stesse curve in scala di VELOCITÀ (senza quadrato): è quello che disegna il pannello ---
    vel = dr["velocity"]
    assert set(vel) == {"oracle", "nowcast", "orange"} and all(len(vel[k]) == len(dts) for k in vel)
    assert blk_cut["direction"]["velocity"]["nowcast"] == vel["nowcast"][:700]
    assert blk_cut["direction"]["velocity"]["orange"] == vel["orange"][:700]
    rv = rb["velocity"]
    for k in ("oracle", "nowcast", "orange"):
        assert abs(rv[k][300] - 0.5) < 0.015, f"su una salita di 0.5 a barra {k} deve valere 0.5, vale {rv[k][300]}"
        assert abs(fb["velocity"][k][300] + 0.5) < 0.015, f"su una discesa {k} deve valere −0.5"
    assert all((a > 0) == (b > 0) for a, b in zip(vel["nowcast"][300:], now[300:]) if b != 0), "stesso segno di velocità ed energia"

    # --- 11. strategia DIREZIONE: dentro finché l'arancione è sopra lo zero (in tempo reale) ---
    from stable_strategy import direction_positions, backtest_direction
    dd = [float("nan")] * 5 + [-1.0] * 5 + [2.0] * 10 + [0.0] + [-3.0] * 9 + [1.0] * 10
    pp = direction_positions(dd)
    assert pp == [0] * 10 + [1] * 10 + [0] * 10 + [1] * 10, "1 solo con scostamento positivo; NaN e zero = fuori"
    dts3 = _dates(40)
    prs3 = [100.0 + i for i in range(40)]
    rdir = backtest_direction(dts3, prs3, dd)
    assert rdir["trades"][0]["entry_date"] == dts3[11], "compra alla chiusura successiva al cambio di segno"
    assert rdir["trades"][0]["exit_date"] == dts3[21], "vende alla chiusura successiva al cambio di segno"
    assert rdir["trades"][1]["entry_date"] == dts3[31] and rdir["trades"][1]["exit_date"] == "OPEN"
    assert "dir" in blk and len(blk["dir"]["trade_pnl_curve"]) == len(dts) and blk["dir"]["stats"]["total_trades"] >= 1
    closed = [(x["entry_date"], x["exit_date"]) for x in blk_cut["dir"]["trades"] if x["exit_date"] != "OPEN"]
    full_tr = [(x["entry_date"], x["exit_date"]) for x in blk["dir"]["trades"]]
    assert closed and all(c in full_tr for c in closed), "le operazioni passate non cambiano quando arrivano nuovi dati"

    # --- 12. LIVE IN TEMPO REALE: la regola dell'oracolo sul freeze, uscita solo quando gira la direzione ---
    from stable_strategy import live_realtime_positions, backtest_live_realtime
    rng = np.random.default_rng(3)
    vel = list(rng.normal(0, 0.02, 300))                 # un anno di velocità piccole e casuali
    vel += [0.5, 0.6, 0.7, 0.8, 0.9]                     # 300-304: il moto accelera verso l'alto → cinetica sopra la media
    vel += [0.3, 0.2, 0.1, 0.05, 0.02]                   # 305-309: rallenta (la cinetica crolla) ma la direzione resta su
    vel += [-0.1, -0.2]                                  # 310-311: la direzione gira
    vel += list(rng.normal(0, 0.02, 40))
    lp = live_realtime_positions(vel)
    assert len(lp) == len(vel) and set(lp) <= {0, 1}
    assert lp[299] == 0 and lp[300] == 1, "entra quando la cinetica supera la propria media con verso in su"
    assert lp[300:310] == [1] * 10, "la pausa (cinetica in calo, direzione ancora su) NON fa uscire"
    assert lp[310] == 0 and lp[311] == 0, "esce quando la direzione gira"
    assert live_realtime_positions(vel[:306]) == lp[:306], "causale: il passato non cambia"
    assert live_realtime_positions([float("nan")] * 50) == [0] * 50
    down = list(rng.normal(0, 0.02, 300)) + [-0.5, -0.6, -0.7, -0.8]
    assert sum(live_realtime_positions(down)[300:]) == 0, "cinetica alta ma verso in giù: niente long"
    dts4 = _dates(len(vel))
    prs4 = [100.0 + 0.2 * i for i in range(len(vel))]
    rl = backtest_live_realtime(dts4, prs4, vel)
    assert rl["trades"][-1]["entry_date"] == dts4[301] and rl["trades"][-1]["exit_date"] == dts4[311]
    assert "live_rt" in blk and len(blk["live_rt"]["trade_pnl_curve"]) == len(dts)
    c_rt = [(x["entry_date"], x["exit_date"]) for x in blk_cut["live_rt"]["trades"] if x["exit_date"] != "OPEN"]
    f_rt = [(x["entry_date"], x["exit_date"]) for x in blk["live_rt"]["trades"]]
    assert all(c in f_rt for c in c_rt), "le operazioni passate non cambiano quando arrivano nuovi dati"

    print("OK test_frozen_v2_rise — stati 0-4, V2 Risalita causale ed eseguita a t+1, direzione blu/arancione | scanner: frozen2 %+.1f%% (espos. %.0f%%), frozen2r %+.1f%% (espos. %.0f%%)"
          % (r["strategies"]["frozen2"]["roi"], r["strategies"]["frozen2"]["expo"], s2r["roi"], s2r["expo"]))


if __name__ == "__main__":
    main()
