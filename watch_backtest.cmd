@echo off
rem Local real-time view of the running backtest / sweep (reads state\backtest_progress.json, no Vercel traffic).
cd /d "%~dp0web"
start "" http://localhost:3000/backtest
npm run dev
