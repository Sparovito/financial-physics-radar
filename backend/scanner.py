"""
Market Scanner with Email Alerts (Strict Separation)
"""
from notifications import NotificationManager
from tickers_loader import load_tickers
import datetime

def run_market_scan(send_email=True):
    from main import analyze_stock, AnalysisRequest
    
    tickers_map = load_tickers()
    tickers = list(tickers_map.keys())
    
    print(f"🔄 Avvio scansione email per {len(tickers)} ticker...")
    
    # LISTE SEPARATE
    buy_today = []
    buy_recent = []
    sell_today = []
    
    errors = []
    
    notifier = NotificationManager()
    today_real = datetime.date.today() # Data reale di oggi
    
    for i, ticker in enumerate(tickers):
        try:
            if i % 20 == 0:
                print(f"   Progresso: {i}/{len(tickers)}...")
            
            # Clean category
            raw_cat = tickers_map.get(ticker, "Other")
            category = raw_cat.replace("⭐ ", "").replace("🏛️ ", "").replace("💻 ", "").replace("🏦 ", "").replace("⚡ ", "")
            
            # ANALISI
            req = AnalysisRequest(
                ticker=ticker,
                alpha=200.0,
                beta=1.0,
                start_date="2023-01-20",
                end_date=None,
                use_cache=True
            )
            result = analyze_stock(req)
            if "error" in result: continue
            
            frozen_trades = result.get("frozen_strategy", {}).get("trades", [])
            sum_trades = result.get("frozen_sum_strategy", {}).get("trades", [])
            
            # Helper date diff
            def get_days_diff(date_str):
                try:
                    d = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
                    return (today_real - d).days
                except:
                    return 999

            # CHECK SIGNALS
            def check_signals(trades, strat_name):
                if not trades: return
                
                last_trade = trades[-1]
                exit_dt = last_trade.get("exit_date")
                entry_date = last_trade.get("entry_date", "")
                direction = last_trade.get("direction", "LONG")
                
                # --- BUY CHECK ---
                # Se è APERTO o appena aperto
                if exit_dt is None or exit_dt == "OPEN":
                    diff = get_days_diff(entry_date)
                    
                    item = {
                        "ticker": ticker,
                        "category": category,
                        "strategy": strat_name,
                        "direction": direction,
                        "price": last_trade.get("entry_price", 0),
                        "date": entry_date,
                        "days_ago": diff
                    }
                    
                    if diff == 0:
                        buy_today.append(item)
                    elif diff <= 5: # Finestra 5 giorni
                        buy_recent.append(item)
                
                # --- SELL CHECK ---
                # Se è CHIUSO e la data di uscita è OGGI
                if exit_dt and exit_dt != "OPEN":
                     diff_exit = get_days_diff(exit_dt)
                     if diff_exit == 0: # Solo se chiuso OGGI
                        sell_today.append({
                            "ticker": ticker,
                            "category": category,
                            "strategy": strat_name,
                            "direction": direction,
                            "price": last_trade.get("exit_price", 0),
                            "pnl": last_trade.get("pnl_pct", 0),
                            "date": exit_dt
                        })

            # Esegui check
            check_signals(frozen_trades, "Frozen")
            check_signals(sum_trades, "Sum")

        except Exception as e:
            continue
            
    # STATISTICHE
    n_buy = len(buy_today)
    n_recent = len(buy_recent)
    n_sell = len(sell_today)
    print(f"✅ Scansione completata: {n_buy} BUY OGGI, {n_recent} RECENTI, {n_sell} SELL OGGI")
    
    # COSTRUZIONE EMAIL
    if n_buy + n_recent + n_sell > 0:
        subject = f"🔔 Report: {n_buy} BUY, {n_sell} SELL ({today_real})"
        
        style = """
        <style>
            body { font-family: Helvetica, sans-serif; background: #f4f4f4; padding: 20px; }
            .container { background: #fff; padding: 20px; border-radius: 8px; max-width: 900px; margin: auto; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
            h2 { border-bottom: 2px solid #ddd; padding-bottom: 10px; color: #333; }
            h3 { margin-top: 25px; margin-bottom: 10px; font-size: 16px; text-transform: uppercase; letter-spacing: 1px; }
            table { width: 100%; border-collapse: collapse; font-size: 14px; margin-bottom: 10px; }
            th { background: #2c3e50; color: #fff; padding: 10px; text-align: left; }
            td { padding: 10px; border-bottom: 1px solid #eee; }
            tr:last-child td { border-bottom: none; }
            
            /* Colors */
            .bg-green { background-color: #e8f5e9; } /* Light Green */
            .bg-yellow { background-color: #fffde7; } /* Light Yellow */
            .bg-red { background-color: #ffebee; }    /* Light Red */
            
            .text-green { color: #2e7d32; font-weight: bold; }
            .text-red { color: #c62828; font-weight: bold; }
            
            .badge { padding: 4px 8px; border-radius: 4px; font-size: 11px; font-weight: bold; color: #fff; background: #78909c; }
        </style>
        """
        
        body = f"<html><head>{style}</head><body><div class='container'>"
        body += f"<h2>📊 Market Report del {today_real}</h2>"
        
        # 1. BUY OGGI
        if buy_today:
            body += "<h3 style='color:#2e7d32;'>🟢 SEGNALI DI INGRESSO (OGGI)</h3>"
            body += "<table><thead><tr><th>Ticker</th><th>Cat</th><th>Strat</th><th>Prezzo</th><th>Data</th></tr></thead><tbody>"
            for a in buy_today:
                cat = a['category'][:12]
                body += f"<tr class='bg-green'><td><b>{a['ticker']}</b></td><td><span class='badge'>{cat}</span></td><td>{a['strategy']}</td><td>${a['price']:.2f}</td><td>OGGI</td></tr>"
            body += "</tbody></table>"
        
        # 2. BUY RECENTI
        if buy_recent:
            buy_recent.sort(key=lambda x: x['days_ago']) # Ordina per più recenti
            body += "<h3 style='color:#f9a825;'>🟡 INGRESSI RECENTI (< 5gg)</h3>"
            body += "<table><thead><tr><th>Ticker</th><th>Cat</th><th>Strat</th><th>Prezzo</th><th>Data</th><th>Giorni fa</th></tr></thead><tbody>"
            for a in buy_recent:
               cat = a['category'][:12]
               body += f"<tr class='bg-yellow'><td><b>{a['ticker']}</b></td><td><span class='badge'>{cat}</span></td><td>{a['strategy']}</td><td>${a['price']:.2f}</td><td>{a['date']}</td><td>-{a['days_ago']}gg</td></tr>"
            body += "</tbody></table>"
            
        # 3. SELL OGGI
        if sell_today:
            body += "<h3 style='color:#c62828;'>🔴 SEGNALI DI USCITA (OGGI)</h3>"
            body += "<table><thead><tr><th>Ticker</th><th>Cat</th><th>Strat</th><th>Prezzo</th><th>P/L %</th></tr></thead><tbody>"
            for a in sell_today:
                pnl_cls = "text-green" if a['pnl'] >= 0 else "text-red"
                cat = a['category'][:12]
                body += f"<tr class='bg-red'><td><b>{a['ticker']}</b></td><td><span class='badge'>{cat}</span></td><td>{a['strategy']}</td><td>${a['price']:.2f}</td><td class='{pnl_cls}'>{a['pnl']:.2f}%</td></tr>"
            body += "</tbody></table>"
            
        body += "<p style='font-size:12px; color:#888; margin-top:30px;'>Generato da Financial Physics AI Scanner</p>"
        body += "</div></body></html>"
        
        if send_email:
            notifier.send_email(subject, body)
        
    else:
        if send_email:
             notifier.send_email(f"Report {today_real}", "<p>Nessun segnale rilevante oggi.</p>")

    return {"buy_today": n_buy, "buy_recent": n_recent, "sell_today": n_sell}


if __name__ == "__main__":
    run_market_scan(send_email=True)
