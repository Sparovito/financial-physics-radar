"""
Market Scanner with Email Alerts (Strict Separation)
"""
from notifications import NotificationManager
from tickers_loader import load_tickers
import datetime

def run_market_scan(send_email=True):
    from main import analyze_stock, AnalysisRequest, PortfolioManager, TICKER_CACHE
    
    tickers_map = load_tickers()
    tickers = list(tickers_map.keys())
    
    print(f"🔄 Avvio scansione email per {len(tickers)} ticker...")
    
    # --- CRITICAL: Invalidate cache for portfolio tickers ---
    # This ensures HOLD/SELL recommendations use FRESH data, not stale cache.
    # Also merges portfolio tickers into scan list to prevent false SELL signals.
    portfolio_tickers = set()
    try:
        pf_mgr = PortfolioManager()
        pf_data = pf_mgr.load()
        portfolio_tickers = set(
            p["ticker"] for p in pf_data.get("positions", [])
            if p.get("status") == "OPEN"
        )
        invalidated = 0
        added = 0
        for t in portfolio_tickers:
            if t in TICKER_CACHE:
                del TICKER_CACHE[t]
                invalidated += 1
            # Ensure portfolio ticker is in scan list (may not be in tickers.js)
            if t not in tickers_map:
                tickers_map[t] = "Portfolio"
                tickers.append(t)
                added += 1
        print(f"🗑️ Cache invalidata per {invalidated}/{len(portfolio_tickers)} ticker del portafoglio")
        if added > 0:
            print(f"➕ Aggiunti {added} ticker del portafoglio non presenti in tickers.js")
    except Exception as e:
        print(f"⚠️ Errore invalidazione cache portafoglio: {e}")
    
    # LISTE SEPARATE
    buy_today = []
    buy_recent = []
    sell_today = []
    
    # NEW: Track active strategies to validate portfolio positions
    active_strategies = set()
    
    errors = []
    
    notifier = NotificationManager()
    today_real = datetime.date.today() # Data reale di oggi
    
    # NEW: Track current prices for portfolio valuation
    ticker_prices = {}
    
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
            
            # Capture Current Price
            if result.get("prices"):
                ticker_prices[ticker] = result["prices"][-1]
            
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
                entry_date = last_trade.get("entry_date", "")
                direction = last_trade.get("direction", "LONG")
                
                # --- ACTIVE STRATEGY CHECK ---
                # If trade is OPEN, record it as active
                if exit_dt is None or exit_dt == "OPEN":
                    active_strategies.add((ticker, strat_name))
                
                # --- BUY CHECK ---
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
                    elif diff <= 5:
                        buy_recent.append(item)
                
                # --- SELL CHECK ---
                if exit_dt and exit_dt != "OPEN":
                     diff_exit = get_days_diff(exit_dt)
                     if diff_exit == 0:
                        sell_today.append({
                            "ticker": ticker,
                            "category": category,
                            "strategy": strat_name,
                            "direction": direction,
                            "price": last_trade.get("exit_price", 0),
                            "pnl": last_trade.get("pnl_pct", 0),
                            "date": exit_dt
                        })

            # Esegui check (NO MA - user requested it only in frontend scanner)
            check_signals(frozen_trades, "Frozen Strategy")
            check_signals(sum_trades, "Sum Strategy")

        except Exception as e:
            continue
    
    # --- PORTFOLIO STATUS CHECK ---
    portfolio_status = []
    try:
        pf_mgr = PortfolioManager()
        pf_data = pf_mgr.load()
        open_positions = [p for p in pf_data.get("positions", []) if p.get("status") == "OPEN"]
        
        # Build set of sell tickers for quick lookup
        sell_set = {(s["ticker"], s["strategy"]) for s in sell_today}
        
        for pos in open_positions:
            ticker = pos.get("ticker", "")
            strategy = pos.get("strategy", "")
            
            # LOGIC:
            # 1. HOLD if strategy is active (Trade is currently open in the logic)
            # 2. SELL if strategy is NOT active (Logic says trade should be closed or never existed)
            
            is_active = (ticker, strategy) in active_strategies
            
            if is_active:
                action = "HOLD"
            else:
                action = "SELL"
            
            # Get Current Price
            curr = ticker_prices.get(ticker, 0)
            entry = pos.get("entry_price", 0) or 0
            
            # Calc PnL
            pnl = 0.0
            if entry > 0 and curr > 0:
                direction = pos.get("direction", "LONG")
                if direction == "LONG":
                     pnl = (curr - entry) / entry * 100
                else:
                     pnl = (entry - curr) / entry * 100
            
            portfolio_status.append({
                "ticker": ticker,
                "strategy": strategy,
                "entry_date": pos.get("entry_date", ""),
                "entry_price": entry,
                "current_price": curr,
                "pnl": pnl,
                "action": action
            })
    except Exception as e:
        print(f"⚠️ Errore caricamento portafoglio: {e}")
            
    # STATISTICHE
    n_buy = len(buy_today)
    n_recent = len(buy_recent)
    n_sell = len(sell_today)
    n_portfolio = len(portfolio_status)
    print(f"✅ Scansione completata: {n_buy} BUY OGGI, {n_recent} RECENTI, {n_sell} SELL OGGI, {n_portfolio} Posizioni")
    
    # COSTRUZIONE EMAIL
    if n_buy + n_recent + n_sell + n_portfolio > 0:
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
            .bg-green { background-color: #e8f5e9; }
            .bg-yellow { background-color: #fffde7; }
            .bg-red { background-color: #ffebee; }
            .bg-blue { background-color: #e3f2fd; }
            
            .text-green { color: #2e7d32; font-weight: bold; }
            .text-red { color: #c62828; font-weight: bold; }
            .text-blue { color: #1565c0; font-weight: bold; }
            
            .badge { padding: 4px 8px; border-radius: 4px; font-size: 11px; font-weight: bold; color: #fff; background: #78909c; }
            .action-sell { background: #c62828; color: #fff; padding: 4px 8px; border-radius: 4px; font-weight: bold; }
            .action-hold { background: #1565c0; color: #fff; padding: 4px 8px; border-radius: 4px; font-weight: bold; }
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
            buy_recent.sort(key=lambda x: x['days_ago'])
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
        
        # 4. PORTFOLIO STATUS (NEW!)
        if portfolio_status:
            # Calc Average PnL (Simple Average)
            avg_val = sum(p['pnl'] for p in portfolio_status) / len(portfolio_status) if portfolio_status else 0
            
            body += "<h3 style='color:#1565c0;'>🔵 IL TUO PORTAFOGLIO</h3>"
            body += f"<p><b>Media PnL:</b> <span class='{'text-green' if avg_val>=0 else 'text-red'}'>{avg_val:.2f}%</span></p>"
            body += "<table><thead><tr><th>Ticker</th><th>Strategia</th><th>Ingresso</th><th>Prezzo Attuale</th><th>Guadagno %</th><th>Azione</th></tr></thead><tbody>"
            for p in portfolio_status:
                action_cls = "action-sell" if p['action'] == "SELL" else "action-hold"
                pnl_cls = "text-green" if p['pnl'] >= 0 else "text-red"
                body += f"<tr class='bg-blue'><td><b>{p['ticker']}</b></td><td>{p['strategy']}</td><td>{p['entry_date']} @ ${p['entry_price']:.2f}</td><td>${p['current_price']:.2f}</td><td class='{pnl_cls}'>{p['pnl']:.2f}%</td><td><span class='{action_cls}'>{p['action']}</span></td></tr>"
            body += "</tbody></table>"
            
        body += "<p style='font-size:12px; color:#888; margin-top:30px;'>Generato da Financial Physics AI Scanner</p>"
        body += "</div></body></html>"
        
        if send_email:
            notifier.send_email(subject, body)
        
    else:
        if send_email:
             notifier.send_email(f"Report {today_real}", "<p>Nessun segnale rilevante oggi.</p>")

    return {
        "buy_today": buy_today, 
        "buy_recent": buy_recent, 
        "sell_today": sell_today, 
        "portfolio": portfolio_status,
        "counts": {
            "buy_today": n_buy,
            "buy_recent": n_recent,
            "sell_today": n_sell,
            "portfolio": n_portfolio
        }
    }


if __name__ == "__main__":
    run_market_scan(send_email=True)
