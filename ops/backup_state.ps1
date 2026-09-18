# Nightly offsite backup of the state files that cannot be rebuilt (2026-09-17): the live ledger, the learner's warm start
# and models, the dashboard payload, caches that carry history, the graph snapshots and the insider files.
# Windows task SemiBand-Backup runs it at 13:50 PT; it needs the Google Cloud SDK logged in to the semiband project.
$ErrorActionPreference = "Continue"
$g = "$env:LOCALAPPDATA\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd"
$S = "C:\Users\calif\Desktop\Trading\state"
$B = "gs://semiband-state-backup/state"
$stamp = (Get-Date).ToString('yyyy-MM-dd HH:mm')
$files = @("ledger.sqlite", "backtest.sqlite", "model.json", "model_raw_shadow.json", "dashboard.json", "universe.json",
           "macro_calendar.json", "guardian_exits.json", "run_daily.log", "guardian.log", "insider_refresh.log")
$n = 0
foreach ($f in $files) {
    $p = Join-Path $S $f
    if (Test-Path $p) { & $g storage cp $p "$B/$f" --quiet 2>$null; $n += 1 }
}
foreach ($d in @("graph_snapshots", "insider")) {
    $p = Join-Path $S $d
    if (Test-Path $p) { & $g storage rsync $p "$B/$d" --recursive --quiet 2>$null }
}
# a dated copy of the live ledger, kept for a month by the bucket's lifecycle rule (set separately)
& $g storage cp (Join-Path $S "ledger.sqlite") "$B/daily/ledger_$((Get-Date).ToString('yyyyMMdd')).sqlite" --quiet 2>$null
"$stamp backup: $n files + graph_snapshots + insider -> $B" | Out-File -Append -Encoding utf8 (Join-Path $S "backup.log")
