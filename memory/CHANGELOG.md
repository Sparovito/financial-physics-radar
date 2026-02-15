# Deployment History

| Deploy ID | Date       | Change                                                                                            |
| --------- | ---------- | ------------------------------------------------------------------------------------------------- |
| PENDING   | 2026-02-15 | Fix: Invalidate TICKER_CACHE for portfolio tickers before email scan (stale data caused wrong HOLD/SELL) |
| PENDING   | 2026-02-15 | Fix: Merge portfolio tickers into scan list (tickers not in tickers.js always showed SELL)         |
| e1f3eb9   | 2026-01-28 | Update: Sync latest changes including portfolio visualization                                     |
| 73281bb   | 2026-01-28 | Fix: Add missing imports for backtest strategies in main.py                                       |
| cde1a8d   | 2026-01-28 | Feat: Enable 5 Fourier scenarios in backend and frontend                                          |
| f4c7ede   | 2026-01-28 | Fix: Make frozen loop transactional and debuggable                                                |
| a1a27e3   | 2026-01-28 | Fix: Add missing import for scipy.signal inside try block                                         |
| decfee2   | 2026-01-28 | Fix: Add mechanics/fourier calculation after time travel (always defined)                         |
| e8b0640   | 2026-01-28 | Fix: Move frozen calculation inside else block (fresh data only)                                  |
| eb7762c   | 2026-01-28 | Fix: Update traceFrozenSum to use frozen_data key                                                 |
| dca3470   | 2026-01-28 | Fix: Critical indentation bug - cache update was inside except block                              |
| 3ec9757   | 2026-01-28 | Fix: Add z_slope to frozen_data in API response                                                   |
| fef76ca   | 2026-01-28 | Fix: Add raw_slope aggregation and proper point-in-time calculation                               |
| e4f97ca   | 2026-01-28 | Fix: Indentation error in frozen loop calculation                                                 |
| 1bfd944   | 2026-01-28 | Feat: Add 'Predictive Slope' (Ghost) indicator to frontend                                        |
| 9353011   | 2026-01-28 | Feat: Implement Frozen Predictive Slope (using internal ghosts) and revert main slope             |
| 6c6c7b7   | 2026-01-28 | Fix: Implement 'Ghost Future' to solve zero-slope boundary condition                              |
| 42ad3b5   | 2026-01-28 | Sync: Update frontend state (cleanup unused options)                                              |
| 54fbfcb   | 2026-01-28 | Fix: Enable event listener for Slope MA toggle                                                    |
| 8840a87   | 2026-01-28 | Fix: Remove undefined showFft variable ensuring app stability                                     |
| 4994cc1   | 2026-01-28 | Feat: Implement independent Slope MA chart support                                                |
| 87076a4   | 2026-01-28 | Feat: Disable ZigZag default, add Slope MA toggle                                                 |
| 5d61af1   | 2026-01-28 | Feat: Add hide/show legend toggle button                                                          |
| 0530e36   | 2026-01-28 | Feat: Implement dynamic chart legend toggle                                                       |
| 0ef1a2e   | 2026-01-28 | Style: Remove (Fresh) text from Analyze button                                                    |
| c353bf3   | 2026-01-28 | Style: Make portfolio chart labels less invasive                                                  |
| a675d73   | 2026-01-28 | Refactor: Analyze button forces refresh, arrows respect checkbox                                  |
| 2b2bdbd   | 2026-01-28 | Fix: Force cache usage when navigating history via arrow keys                                     |
| 12192e1   | 2026-01-28 | Feat: Allow runAnalysis to accept forceCache parameter                                            |
| 064f841   | 2026-01-28 | Fix: Disable cache by default in UI for fresh data analysis                                       |
| bd6ad0e   | 2026-01-28 | Debug: Add logging of last fetched date in logic.py                                               |
| be0386b   | 2026-01-28 | Fix: Invalidate cache if data is older than 3 days                                                |
| 2a88ecc   | 2026-01-24 | Fix: Bump app.js to v11                                                                           |
| ba00bb4   | 2026-01-24 | Feat: Add portfolio scatter trace to chart rendering                                              |
| da432c5   | 2026-01-24 | Refactor: Use scatter trace for portfolio markers (dots) instead of shapes                        |
| f4cd545   | 2026-01-24 | Fix: Call fetchPortfolioData on window load                                                       |
| 92521fc   | 2026-01-24 | Fix: Bump app.js to v10 to reload portfolio visualization                                         |
| 00aafca   | 2026-01-24 | Feat: Add portfolio text annotations to chart                                                     |
| 2419c64   | 2026-01-24 | Feat: Implement getPortfolioMarkers for chart visualization                                       |
| 7710af2   | 2026-01-24 | Refactor: distinct fetchPortfolioData function with global storage                                |
| 802eac0   | 2026-01-24 | Fix: Add missing closePortfolioModal function                                                     |
| 1d1599b   | 2026-01-24 | Enhance: Replace portfolio link with Analyze button                                               |
| f98acdd   | 2026-01-24 | Fix: Bump app.js version to v9 to force cache reload                                              |
| 63e3010   | 2026-01-24 | Fix: Remove stray code from app.js                                                                |
| f8991a2   | 2026-01-24 | Feat: Add pfAnalyzeTicker function to portfolio                                                   |
| 974b58d   | 2026-01-24 | Enhance: Portfolio average return and clickable tickers                                           |
| b4ecb7d   | 2026-01-22 | Fix: Use fixed colors for trade markers (green entry, red exit)                                   |
| 16bed67   | 2026-01-22 | Fix: Trade markers now use correct data variable (LAST_ANALYSIS_DATA)                             |
| 9ae68dc   | 2026-01-22 | Feature: Add trade markers on price chart with strategy selector                                  |
| fe73a38   | 2026-01-22 | Feature: Dynamic averages in scanner + wider modal                                                |
| 17774bb   | 2026-01-22 | UI: Use clearer Unicode arrows for trend indicator                                                |
| 23f4e7e   | 2026-01-22 | Feature: Replace Kin/Cap with Price Trend indicator in scanner                                    |
| e5a27d8   | 2026-01-21 | Chore: Update scheduler time to 16:30                                                             |
| 85b0873   | 2026-01-21 | Feature: Add MA strategy to frontend scanner (not email)                                          |
| c9d1dd5   | 2026-01-20 | Feature: Add MA strategy to market scanner                                                        |
| bc5c491   | 2026-01-20 | Fix: MA trace uses trade_pnl_curve (consistent with other strategies)                             |
| d9451ad   | 2026-01-20 | Fix: Use equity_curve key for MA strategy trace (matches backend)                                 |
| 2ff8d13   | 2026-01-20 | Fix: MA strategy P/L trace on correct Y-axis (y5)                                                 |
| 8a8ba9f   | 2026-01-20 | Fix: MA strategy exit now uses Z-threshold (matches SUM timing)                                   |
| c4f3072   | 2026-01-20 | Fix: Remove stray code blocking frontend execution                                                |
| bef122f   | 2026-01-20 | Fix: Initialize MA key in ORIGINAL_TRADES to prevent JS crash                                     |
| da55a12   | 2026-01-20 | Fix: Enable Trades View for MA Strategy in frontend                                               |
| 444e2e8   | 2026-01-20 | Refactor: Implement Hybrid Min Action Strategy (Sum-Z Timing + Curve Direction)                   |
| 23c20cd   | 2026-01-20 | Fix: Logic for PRICE_VS_CURVE strategy mode (Min Action)                                          |
| 396ee89   | 2026-01-20 | Fix: Handle empty Z-arrays in trend_curve backtest mode                                           |
| f7bfc4c   | 2026-01-20 | Fix: Backend missing Min Action logic & Frontend undefined ref                                    |
| 9f8d148   | 2026-01-20 | Style: Change Min Action Strategy color from Green to Blue                                        |
| 67cec8d   | 2026-01-20 | Feat: Add Frontend visualization for Min Action Strategy (Green Line)                             |
| ee71052   | 2026-01-20 | Feat: Add Min Action Strategy (Green Line) to backend analysis                                    |
| 5d27035   | 2026-01-20 | Fix: Add explicit timezone to CronTrigger to fix scheduling bug (test 20:12)                      |
| ed3868e   | 2026-01-20 | Debug: Add /scheduler-status endpoint and detailed logging for APScheduler diagnosis (test 20:05) |
| 78a6f06   | 2026-01-20 | Test: Andrea's signature test for 19:56                                                           |
| c958bfd   | 2026-01-20 | Fix: Add robust error logging and stdout flush to scheduled job                                   |
| 5a966bb   | 2026-01-20 | Config: Final Clean Revert to 18:30 CET (Production)                                              |
| 229bc0a   | 2026-01-20 | Test: Andrea's manual test for 19:46 with custom log message                                      |
| c8694a0   | 2026-01-20 | Config: Final Revert to 18:30 CET (Production Ready)                                              |
| 2eefe1c   | 2026-01-20 | Test: Set scheduler to 19:35 CET (FINAL TEST)                                                     |
| ce320a6   | 2026-01-20 | Config: Final Revert to 18:30 CET for daily production schedule                                   |
| 883063a   | 2026-01-20 | Test: Set scheduler to 19:15 CET (PRECISO)                                                        |
| c020d52   | 2026-01-20 | Test: Set scheduler to 19:08 CET (VERY URGENT)                                                    |
| 056685a   | 2026-01-20 | Test: Set scheduler to 19:02 CET (URGENT)                                                         |
| b54a57a   | 2026-01-20 | Config: Set daily email scheduler to 18:30 CET (Production)                                       |
| 822d2c8   | 2026-01-20 | Fix: Resolve datetime import error and set test schedule to 19:00                                 |
| 7d1d437   | 2026-01-20 | Fix: Add pytz dependency for timezone handling                                                    |
| b0e4458   | 2026-01-20 | Test: Set scheduler to 18:50 CET                                                                  |
| a852b5a   | 2026-01-20 | Feat: Add /debug-time endpoint and tzdata for scheduler debugging                                 |
| cca3846   | 2026-01-20 | Test: Change scheduler to 18:40 for testing                                                       |
| ca424e4   | 2026-01-20 | Feat: Add daily scheduled email scan at 18:30 (APScheduler)                                       |
| af08dfa   | 2026-01-20 | Feat: Add Portfolio Status table to email report (SELL/HOLD)                                      |
| c7f6910   | 2026-01-20 | Feat: Switch to Resend API for email (bypass Railway SMTP block)                                  |
| 605428f   | 2026-01-20 | Fix: Support SMTP_SSL for port 465 (Bypass Railway firewall)                                      |
| ade707d   | 2026-01-20 | Fix: Add firebase-admin to root requirements.txt for Railway                                      |
| c47098c   | 2026-01-20 | Fix: Remove duplicate firebase-admin from requirements                                            |
| 4796aa7   | 2026-01-20 | Feat: Support Base64 Firebase Credentials for Railway                                             |
| bcbf6bf   | 2026-01-20 | Feat: Email Scanner (HTML Report, Categories) & Firebase Integration                              |
| 900f055   | 2026-01-20 | Feat: Complete Portfolio Simulation (UI, Backend, Editing)                                        |
| 49154b0   | 2026-01-20 | feat(scanner): implement daily signal scanner (Enter/Exit/Hold)                                   |
| 37a0562   | 2026-01-20 | feat(verify): hide blocked trades from integrity report to prevent confusion                      |
| d048e6b   | 2026-01-20 | feat(verify): fuzzy match for dissolved trades blocked by position                                |
| 340cbec   | 2026-01-20 | feat(verify): distinguish between dissolved trades and trades blocked by open positions           |
| 720bc8b   | 2026-01-20 | fix(backend): align SUM strategy verify logic with analyze_stock                                  |
| d6cdbcf   | 2026-01-20 | fix(backend): unify resurrection logic, remove duplicate RE-APPEARED tag                          |
| 3d57c5d   | 2026-01-20 | fix(backend): remove legacy cache check causing NoneType error in verify                          |
| 61af354   | 2026-01-20 | fix(backend): use TICKER_CACHE instead of undefined CACHE var                                     |
| 449c697   | 2026-01-20 | fix(backend): fix NameError for full_frozen_data in verify_trade_integrity                        |
| cfb6fb9   | 2026-01-20 | fix(backend): align FROZEN verify logic with analyze_stock (use Potential + Pre-Pad)              |
| cbe2ef1   | 2026-01-20 | fix(backend): implement trade resurrection logic to distinguish dissolved vs unstable             |
| d5123cc   | 2026-01-20 | fix(backend): restore missing variable definitions for SUM strategy integrity check               |
| 66d9da2   | 2026-01-20 | fix(backend): fix list index out of range by padding frozen signals                               |
| 431520f   | 2026-01-20 | feat(backend): implement true point-in-time simulation for time travel chart                      |
| 139b494   | 2026-01-20 | fix(backend): calculate z_slope dynamically in integrity check to resolve NameError               |
| 85b1998   | 2026-01-20 | fix(backend): resolve NameError by defining price_real in correct scope                           |
| 26cfc1b   | 2026-01-20 | fix(backend): correct verification logic for FROZEN strategy using point-in-time data             |
| 90d5429   | 2026-01-20 | fix(backend): handle partial cache miss to prevent crash in analyzer                              |
| cf0707f   | 2026-01-20 | fix(backend): force long history download for integrity check to prevent empty runs               |
| f8a976b   | 2026-01-20 | fix(config): enforce single worker to ensure shared cache consistency                             |
| 313d862   | 2026-01-20 | fix: prevent verify endpoint from polluting cache with insufficient data                          |
| 06713db   | 2026-01-20 | fix: remove duplicate if statement causing indentation error                                      |
| f015340   | 2026-01-20 | fix(backend): correct ActionPath init and MarketData fetch calls in verify endpoint               |
| 3fd6da6   | 2026-01-20 | fix(backend): correct cache access in verify endpoint (dict vs series)                            |
| 0a2d96f   | 2026-01-20 | fix(js): solve crash in verify button (wrong element IDs)                                         |
| 28efce0   | 2026-01-20 | debug: add logs to verify integrity button                                                        |
| 1cfb45d   | 2026-01-20 | feat: stronger integrity check (1-day step + disappearing trades detection)                       |
| d8c9307   | 2026-01-20 | feat: add trade integrity verification (detects look-ahead bias)                                  |
| a33b370   | 2026-01-20 | fix: ignore OPEN→date as normal trade closure, not retroactive change                            |
| 1eadfdc   | 2026-01-20 | feat: persistent baseline comparison - warnings never disappear                                   |
| daf73e3   | 2026-01-20 | simplify: remove confusing Z-ROC invertito check                                                  |
| bb3a058   | 2026-01-20 | feat: complete trade change detection - entry/exit/direction                                      |
| 14cf42b   | 2026-01-20 | feat: add snapshot warning system to detect retroactive trade changes                             |
| 5ecc099   | 2026-01-20 | fix: separate direction logic - LIVE uses z_slope, Frozen/SUM use Z-ROC                           |
| da197fe   | 2026-01-20 | fix: use Z-ROC for direction (eliminates look-ahead bias)                                         |
| 62d7a89   | 2026-01-19 | feat: add SUM strategy columns to scanner table                                                   |
| c9aaf23   | 2026-01-19 | feat: add SUM strategy to scanner with Orange/Red P/L display                                     |
| d6be4b6   | 2026-01-19 | feat: add SUM strategy to stats panel and trades modal                                            |
| ac4150d   | 2026-01-19 | fix: use -999 padding for Frozen Sum to prevent false signals                                     |
| 03a9890   | 2026-01-19 | feat: add threshold parameter to backtest, set -0.3 for Frozen Sum Strategy                       |
| bbc0c8c   | 2026-01-19 | fix: add traceFrozenSumStrat to traces array                                                      |
| 4e4aa85   | 2026-01-19 | feat: add Frozen Sum investment strategy (third backtest)                                         |
| 9fe2ca9   | 2026-01-19 | feat: add zero-phase low-pass filter to smooth Frozen Sum Z                                       |
| 7d5bc0f   | 2026-01-19 | feat: enable Kinetic Z by default, implement Frozen Sum Index                                     |
| 5a0f0c1   | 2026-01-19 | Feat: Volume Chart overlay, Backend fixes, UI Refactoring                                         |
| 3231809   | 2026-01-19 | Fix: Resolved UnboundLocalError and added Color-coded Volume Bars                                 |
| d147319   | 2026-01-19 | UI: Changed Volume icon to 📶 and enabled by default                                              |
| 007b508   | 2026-01-19 | Fix: Resolved NameError crash and implemented safe Volume extraction                              |
| d4d6cb9   | 2026-01-19 | Fix: Removed syntax error in logic.py                                                             |
| 630a300   | 2026-01-19 | Feat: Added Volume Chart overlay with toggle                                                      |
| 10b4f97   | 2026-01-19 | UI: Reordered sidebar - Historical Simulation moved to top of config section                      |
| 3401e2a   | 2026-01-19 | UI: Reordered sidebar - Config params moved to bottom, History first                              |
| bb05804   | 2026-01-19 | UI: Restored simulation results stats and trades button to main sidebar                           |
| c223994   | 2026-01-19 | Logic: Updated Frozen Potential Density to use Max(30d) instead of instantaneous value            |
| fef9c29   | 2026-01-19 | Backup: Syncing notebooks and test scripts                                                        |
| 9cffbfb   | 2026-01-19 | Feat: Added Blue and Purple annotation options                                                    |
| e96a29a   | 2026-01-19 | Update mobile CSS layout parameters                                                               |
| c6e896b   | 2026-01-19 | Fix CSS mobile: Use 100dvh and flex-grow for full screen chart without gaps                       |
| b5eef53   | 2026-01-19 | Fix CSS mobile: Enabled dynamic height and restored sidebar visibility                            |
| 2855ead   | 2026-01-19 | Fix layout: Removed fixed mobile height, hidden legend on mobile, cleaned redundant config        |
| 8569013   | 2026-01-19 | Fix: Mobile layout - hide toggle sidebar, fix chart height to fill viewport                       |
| 6c3bf65   | 2026-01-19 | Feat: Clickable vertical annotations (green/red lines) with localStorage persistence              |
| 3d2e750   | 2026-01-19 | Fix: Removed duplicate wrapper div for proper chart width                                         |
| 3d456c9   | 2026-01-19 | Fix: Forced chart container width to 100% and autosize=true                                       |
| 52dbfaa   | 2026-01-19 | UI: Compact toggle sidebar (auto height) to reduce space usage                                    |
| db4bea5   | 2026-01-19 | UI: Refined toggle sidebar (centered handle, flat arrows) and fixed duplicate backtest ID         |
| da87f24   | 2026-01-19 | Fix: Coordinate JS arrow symbols with CSS flat style (❮/❯)                                      |
| 7b4a11a   | 2026-01-19 | Feat: Refined sidebar toggle UI (centered, flat arrow)                                            |
| a83b01c   | 2026-01-19 | Feat: Collapsible toggle sidebar and fixed backtest visibility logic                              |
| 76ff242   | 2026-01-19 | Fix: Move toggle reading before domain calculation to fix initialization error                    |
| c8b63d7   | 2026-01-19 | Feat: Moved toggles to left of chart, dynamic space redistribution                                |
| b3a88e8   | 2026-01-19 | Feat: Added chart visibility toggles (Price, Energy, Frozen, Indicators, ZigZag)                  |
| 71d445b   | 2026-01-19 | Feat: ZigZag now uses hourly data aggregated per day (+4, -2, etc.)                               |
| da1f42f   | 2026-01-19 | Fix: Move ZigZag trace after traces array init to avoid reference error                           |
| 3c2c34a   | 2026-01-19 | Fix: Move ZigZag trace outside showBacktest block so it always renders                            |
| 636288c   | 2026-01-19 | Feat: Added Cumulative Direction ZigZag Indicator                                                 |
| c695162   | 2026-01-19 | Fix: Ensure backtest strategy logic consistency                                                   |
| dcdeaf9   | 2026-01-19 | Feat: Shifted Frozen Kinetic storage to T-24 days (lagged) per request                            |
| 1e4baef   | 2026-01-19 | Feat: Shift Kinetic Energy (Green Line) by 24 days as requested                                   |
| 7fa153a   | 2026-01-18 | Fix: Sample Frozen Signal at T-24 to avoid zero-boundary effect (Logic & Main)                    |
| cdf0804   | 2026-01-18 | UI: Added Price to Frozen Radar Focus label (e.g. AAPL [] [+5%])                                  |
| f8ef324   | 2026-01-18 | Feat: Accurate point-in-time Frozen calculation in Scanner (matches Main Chart)                   |
| 48fb538   | 2026-01-18 | UI: Show Z-Score in Focus label instead of P/L (P/L calc differs from Main Chart)                 |
| 98cc084   | 2026-01-18 | Fix: Use trade_pnl_curve (single trade P/L, resets to 0) instead of equity_curve for Radar        |
| 8ea25e9   | 2026-01-18 | Feat: Added ⭐ Highlights category to Radar dropdown                                              |
| b8a9837   | 2026-01-18 | Fix: Restored missing trade_pnl_curve initialization in backtest_strategy                         |
| 26c66fc   | 2026-01-18 | Fix: Removed syntax error (extra brace) in backend/logic.py                                       |
| a659402   | 2026-01-18 | Fix: Resolved TypeError in backtest strategy due to None dates (preventing crash)                 |
| 464b282   | 2026-01-18 | Fix: Radar now displays Cumulative Strategy Equity P/L instead of Single Trade P/L                |
| 0a4fe77   | 2026-01-18 | Feat: Implemented real backend Strategy P/L calculation for Frozen view                           |
| 4942905   | 2026-01-18 | Fix: Restored Gold highlights in filter menu and fixed default category key                       |
| 0a4c24e   | 2026-01-18 | UI: Restrict P/L display to focused ticker and enhance highlight visibility                       |
| 9092c49   | 2026-01-18 | Feat: Frozen view now displays Trade P/L % in labels (Yellow Line logic)                          |
| e833e3b   | 2026-01-18 | UI: Added numerical Z-score values to Frozen view labels                                          |
| f93d25d   | 2026-01-18 | Feat: Implement Focus Mode in Frozen view (dimming + highlighting)                                |
| b65f00e   | 2026-01-18 | Fix: Added z_kin_frozen to scanner results (using Potential Z-Score)                              |
| 095c833   | 2026-01-18 | Fix: Initial radar render now respects Frozen toggle state                                        |
| 9cfea4c   | 2026-01-18 | Fix: Frozen view now correctly reads z_kin_frozen from RADAR_RESULTS_CACHE                        |
| 51ffe13   | 2026-01-18 | UI: Replaced checkbox with visual toggle switch for Frozen mode                                   |
| 2b4f63b   | 2026-01-18 | Feat: Frozen Z-Score 1D line visualization with toggle switch                                     |
| 2b29e51   | 2026-01-18 | Revert: Back to 4 workers, removed x8 option (CPU limited)                                        |
| e0b5c80   | 2026-01-18 | Perf: Increased Uvicorn workers to 8                                                              |
| d295b07   | 2026-01-18 | Perf: Enabled 4 Uvicorn workers for true parallel request processing                              |
| b2b6cb8   | 2026-01-18 | Style: Made unrealized jump more visible (orange, thicker, diamond markers)                       |
| 6d929c9   | 2026-01-18 | Fix: Unrealized profit now shown as final jump segment only (cleaner)                             |
| 54131bc   | 2026-01-18 | Feat: Dual-line equity chart (Realized=green, Total+Unrealized=blue dashed)                       |
| 47a4d1f   | 2026-01-18 | Fix: Simulator charts now respect scanner time window selection                                   |
| eb95693   | 2026-01-18 | Feat: Parallel scanner - batch processing with configurable concurrency (x1-x8)                   |
| 62410ac   | 2026-01-18 | Feat: Added # Trades column to Scanner table                                                      |
| f4e414d   | 2026-01-18 | Fix: Save ticker_obj as instance variable for Market Cap access                                   |
| b931825   | 2026-01-18 | Fix: Corrected Market Cap logic based on yfinance diagnostic (uses .shares, info fallback)        |
| a0eb32c   | 2026-01-18 | Fix: Robust Market Cap fetching with 4-level fallback (ETFs support)                              |
| 8a9a41b   | 2026-01-18 | Fix: Used correct attribute access for fast_info.market_cap                                       |
| 8108e28   | 2026-01-18 | Fix: Corrected Scanner Table footer colspan alignment                                             |
| badf381   | 2026-01-18 | Fix: Switched to yfinance fast_info for reliable Market Cap fetching                              |
| 558da62   | 2026-01-18 | Feat: Added real-time filtering for scanner results (Kinetic/MarketCap)                           |
| f27c272   | 2026-01-18 | Feat: Added Kinetic Energy Index and Market Cap columns to Scanner                                |
| b6f465d   | 2026-01-18 | Feat: Set Frozen as default simulation mode and added red alert background for Live mode          |
| abfcdad   | 2026-01-18 | Feat: Added Simulation Mode Switch (Live v Frozen) to compare optimistic vs realistic backtests   |
| bca6f2a   | 2026-01-18 | Feat: Added selection checkboxes to scanner results for custom portfolio simulation               |
| a8b60ed   | 2026-01-18 | Fix: Cache invalidation logic to support extending history duration                               |
| a9e0337   | 2026-01-18 | Feat: Added configurable history lookback period (years) in UI                                    |
| 060b149   | 2026-01-18 | Feat: Added detailed Trade List table to Portfolio Simulator                                      |
| e596fe9   | 2026-01-18 | Fix: Corrected trade property name to pnl_pct for portfolio simulation                            |
| 4404700   | 2026-01-18 | Fix: Restored missing tickers.js script tag                                                       |
| b830d9d   | 2026-01-18 | Fix: Resolved syntax error in app.js causing unresponsive UI                                      |
| 6261b79   | 2026-01-18 | Feat: Portfolio Simulator (Popup of Popup) with Equity & Exposure Charts                          |
| 5b5bae8   | 2026-01-17 | Fix: Force min-width on mobile table to prevent layout squashing                                  |
| 78b0770   | 2026-01-17 | Fix: Unified mobile table padding logic to prevent misalignment                                   |
| f37886d   | 2026-01-17 | Fix: Mobile Table Header Misalignment (Removed display:block)                                     |
| 9a0977a   | 2026-01-17 | UI: Fix Mobile Table Headers (Shortened, Proper Scroll)                                           |
| d3b7dd6   | 2026-01-17 | UI: Restore True Inline Desktop Layout (Matches Screenshot 2)                                     |
| a44f878   | 2026-01-17 | UI: True Single-Line Desktop Layout (Hide Labels)                                                 |
| 66a069d   | 2026-01-17 | UI: Desktop Horizontal Layout for Scanner                                                         |
| 9c1eb37   | 2026-01-17 | UI: Complete Scanner Redesign (Card Layout, Labels, Gradient Button)                              |
| dc6310d   | 2026-01-17 | UI: Refine Mobile Scanner Layout (Spacing, Touch Targets)                                         |
| 2445027   | 2026-01-17 | Style: Mobile Optimization for Scanner Modal                                                      |
| ebdd6b9   | 2026-01-17 | Fix: Mobile Scanner Network Issue (Use relative API path)                                         |
| cff80ce   | 2026-01-17 | Fix: Total Return calculation (Inflation bug)                                                     |
| e2daf0f   | 2026-01-17 | Fix: SyntaxError in logic.py due to bad copy-paste                                                |
| ce39269   | 2026-01-17 | Fix: Propagate Start/End Date to Backtest Strategy                                                |
| d59dbb4   | 2026-01-17 | Feat: Add Date Range Filter to Bulk Scanner                                                       |
| 3d22008   | 2026-01-17 | Feat: Add Average Stats Row to Bulk Scanner                                                       |
| 0d41ae9   | 2026-01-17 | Feat: Implement Bulk Strategy Scanner (Massive Analysis)                                          |
| a71fb2a   | 2026-01-17 | Refactor: Limit Fourier Analysis to last 1 year (252 days) for better relevance                   |
| 1a3cb0f   | 2026-01-17 | Feat: Visualize Open Trades in History with performance tracking                                  |
| 2bf21bc   | 2026-01-17 | Feat: Add Trades Switch to Modal (Live vs Frozen) and Global Trade Storage                        |
| 114c70c   | 2026-01-17 | Fix: Align Frozen Series length for Backtest to prevent IndexError                                |
| b618b58   | 2026-01-17 | Feat: Add Investment Strategy based on Frozen Potential (Unbiased Backtest)                       |
| 5a7fab1   | 2026-01-17 | Feat: Add Keyboard Navigation (Arrows) with Throttling for smooth history scrolling               |
| 68b6cb7   | 2026-01-17 | Perf: Optimize Historical Sim with Pre-calculated Frozen History (Instant Navigation)             |
| 8213edc   | 2026-01-17 | Feat: Implement Fast Mode (Cache) for historical simulation                                       |
| fab7e07   | 2026-01-17 | Fix: Set SAMPLE_EVERY=1 for max precision (daily) in Frozen Chart                                 |
| ecdea75   | 2026-01-17 | Fix: Switch Frozen Chart to use raw Density (not Z-Score) for direct comparison                   |
| baad27b   | 2026-01-17 | Feat: Add dedicated Frozen Energy panel with filled areas                                         |
| 6c172ea   | 2026-01-17 | Feat: Add frozen Z-Score chart (point-in-time values, no look-ahead bias)                         |
| 559c55f   | 2026-01-17 | Feat: Add Z-ROC (Rate of Change) indicator - no look-ahead bias                                   |
| 843bfed   | 2026-01-17 | Fix: Implement rolling Z-Score (252-day window) to eliminate look-ahead bias                      |
| 450a0a2   | 2026-01-17 | Feat: Add arrow buttons to shift date by day and re-run analysis                                  |
| 4279581   | 2026-01-17 | Feat: Add historical date filter to simulate past (backtest validation)                           |
| d5d4c1a   | 2026-01-17 | Feat: Color radar focused ticker label based on P/L (green/red/white)                             |
| ab595b5   | 2026-01-17 | Fix: Rewrite radar P/L calculation to simulate backtest forward, matching backend exactly         |
| c2f5d58   | 2026-01-17 | Fix: Calculate real trade P/L % in radar using backtest logic (0 when not invested)               |
| 247be99   | 2026-01-17 | Fix: Replace emoji with percentage format for Z-Slope in radar focus label                        |
| 17516a7   | 2026-01-17 | Style: Improve backtest section aesthetics with gradient, border-left accent, and better layout   |
| 2125176   | 2026-01-17 | Feat: Add trades history modal with detailed trade list                                           |
| 39b9df4   | 2026-01-17 | Feat: Add Z-Slope with green/red indicator to radar focused ticker label                          |
| 95f116a   | 2026-01-17 | Refactor: Change backtest chart to show individual trade P/L % (0 when not invested)              |
| 76b9b82   | 2026-01-17 | Feat: Add backtesting strategy simulator with equity curve chart                                  |
| 1c20ca8   | 2026-01-17 | Feat: Show price in brackets when ticker is focused in radar                                      |
| 589766f   | 2026-01-17 | Feat: Add extended ticker name in analysis title + fix category dropdown                          |
| 8b0e4d5   | 2026-01-17 | Fix: Update radar category dropdown and mapping for new 27-category structure                     |
| 02b19c9   | 2026-01-17 | Feat: Add daily cache (localStorage) and animated progress bar to Radar scan                      |
| 4733036   | 2026-01-17 | Feat: Expand to 654 globally traded stocks across 27 categories                                   |
| b3e9bda   | 2026-01-17 | Feat: Extend radar timeline to 3 years (756 days) to reach 2023                                   |
| 7ea2377   | 2026-01-17 | Feat: Use backend Z-Slope for radar bubble color (minima azione dX)                               |
| 55ac2fe   | 2026-01-17 | Fix: Colorbar labels to Slope (20d) and adjusted range                                            |
| f61fc9c   | 2026-01-17 | Feat: Use linear regression slope on Z-Pot for color (minima azione)                              |
| c468906   | 2026-01-17 | Feat: Bubble color now shows 10-day momentum (RdYlGn colorscale)                                  |
| 4d56b93   | 2026-01-17 | Feat: Add Analyze button for focused ticker in Radar                                              |
| c9d5516   | 2026-01-17 | Fix: Hide labels of non-focused tickers in Focus Mode                                             |
| 53f52b5   | 2026-01-17 | Cache bust v6 for Focus Mode                                                                      |
| d6f4322   | 2026-01-17 | Feat: Add Focus Mode to Radar - Click to focus a ticker, others fade, double-click for analysis   |
| 4b66cdd   | 2026-01-17 | Cache bust v5                                                                                     |
| 5a37816   | 2026-01-17 | Fix: Correct Radar DOM structure - Fullscreen Area wraps Controls + Chart                         |
| d085c36   | 2026-01-17 | Fix: Clean up and organize Desktop Radar controls layout                                          |
| 9862b95   | 2026-01-17 | Fix: Make radar timeline controls compact and pill-shaped on mobile fullscreen                    |
| d8f3390   | 2026-01-17 | Feat: Radar fullscreen now includes timeline slider and trail checkbox                            |
| 671c147   | 2026-01-17 | Fix: DOUBLED chart height to 200% viewport                                                        |
| 7b1c7c5   | 2026-01-17 | Fix: Use 100% viewport height for mobile chart                                                    |
| 9d1a25a   | 2026-01-17 | Fix: Plotly chart now fills container height completely                                           |
| 11b5074   | 2026-01-17 | Fix: Use viewport height (vh) for dynamic chart sizing on mobile                                  |
| 46e3c37   | 2026-01-17 | Fix: Force chart container to 1400px min-height on mobile and remove 60vh limit                   |
| a991180   | 2026-01-17 | Fix: Uncap chart container height in CSS and bump cache to v4                                     |
| 6b0d85d   | 2026-01-17 | Fix: Vertically stack subplots in 1400px container for mobile                                     |
| 4c65172   | 2026-01-17 | Fix: Overwrite index.html with cache busting v3                                                   |
| ac907b2   | 2026-01-17 | Fix: Force hide legend via CSS and bump cache to v3 (Retry)                                       |
| 28e7859   | 2026-01-17 | Fix: Force hide legend CSS and bump cache to v3                                                   |
| 3c8cb6a   | 2026-01-17 | Fix: Aggressively hide legend via CSS and bump cache to v3                                        |
| 667214e   | 2026-01-17 | Fix: Remove Legend and Modebar on mobile for cleaner view                                         |
| 29ecedd   | 2026-01-17 | Fix: Add iOS pseudo-fullscreen fallback (CSS only)                                                |
| a09318d   | 2026-01-17 | Fix: Overwrite index.html with cache busting (?v=2) to resolve visibility issues                  |
| 534073f   | 2026-01-17 | Fix: Refactor Main Chart HTML to include Fullscreen button                                        |
| 26faf8c   | 2026-01-17 | Fix: Cache bust assets and improve Fullscreen button visibility (Gold border, lower position)     |
| e9431ec   | 2026-01-17 | Feat: Add Fullscreen button to Radar and increase z-index for visibility                          |
| af117a2   | 2026-01-17 | Feat: Implement logic for Full Screen chart mode                                                  |
| 28e3e79   | 2026-01-17 | Feat: Add Full Screen mode button for charts                                                      |
| 11e0b80   | 2026-01-17 | Fix: Force 1200px height via JS to bypass cache                                                   |
| 6acc251   | 2026-01-17 | Fix: Move Radar legend below colorbar on mobile                                                   |
| 5de2697   | 2026-01-17 | Fix: Optimize Radar Chart layout for mobile readability                                           |
| 701cdb8   | 2026-01-17 | Fix: Increase mobile chart height to 1200px                                                       |
| 2fba673   | 2026-01-17 | Fix: Improve mobile chart readability with 800px height and better legend placement               |
| 2309d0a   | 2026-01-17 | Feat: Add mobile responsiveness and optimize layout for smartphones                               |
| 9fdb4d4   | 2026-01-16 | Fix: Add backend directory to sys.path to resolve imports on Railway                              |
| d711ed9   | 2026-01-16 | Fix: Use Plotly.newPlot instead of react for radar stability                                      |
| 927316c   | 2026-01-16 | Fix: Complete rewrite of app.js logic to fix radar loading freeze and padded data handling        |
| e8ece64   | 2026-01-16 | Fix: Explicitly fetch DOM elements in app.js to prevent ReferenceErrors                           |
| 575da25   | 2026-01-16 | Dev: Update start_app.sh to use unified port 8000 for frontend and backend                        |
| 630d79b   | 2026-01-16 | Fix: Use absolute paths for frontend directory to resolve 'Directory does not exist' error        |
| e023be1   | 2026-01-16 | Fix: Restore missing FastAPI app initialization and organize imports                              |
| 740baa3   | 2026-01-16 | Fix: Route precedence in main.py, Add README.md                                                   |
| 88d2533   | 2026-01-16 | Chore: Prepare for Railway deployment (Procfile, Static Serving)                                  |
| 7c3db84   | 2026-01-16 | Initial commit: Financial Physics Web App - Market Radar & Time Travel                            |



## Changelog Policy

- Le versioni precedenti NON devono essere riscritte.
- Le decisioni storiche sono considerate vincolanti.
- Ogni nuova modifica va aggiunta in fondo, non retroattivamente.
- I coding agent non devono:
  - reinterpretare versioni passate,
  - “ottimizzare” decisioni storiche,
  - riscrivere il changelog senza richiesta esplicita.
