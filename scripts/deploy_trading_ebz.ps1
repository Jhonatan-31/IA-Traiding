# Deploy AI Trading Bot Pro to EBZ — isolated from Consultate/EVS.
# Usage (from repo root):
#   powershell -ExecutionPolicy Bypass -File scripts/deploy_trading_ebz.ps1

param(
  [string]$RemoteHost = "consultate",
  [string]$RemoteDir = "/srv/apps/ia-bot-trading",
  [switch]$SkipBuild
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$ComposeRel = "deploy/ebz/docker-compose.yml"

function Invoke-Remote([string]$Bash) {
  # Avoid PowerShell CRLF/BOM breaking remote bash.
  $normalized = ($Bash -replace "`r`n", "`n" -replace "`r", "`n").TrimStart([char]0xFEFF)
  $localSh = Join-Path $env:TEMP ("ebz-remote-" + [guid]::NewGuid().ToString("N") + ".sh")
  $utf8NoBom = New-Object System.Text.UTF8Encoding $false
  [System.IO.File]::WriteAllText($localSh, $normalized + "`n", $utf8NoBom)
  try {
    scp -o BatchMode=yes $localSh "${RemoteHost}:/tmp/ebz-remote.sh"
    if ($LASTEXITCODE -ne 0) { throw "scp script remoto falló" }
    ssh -o BatchMode=yes -o ConnectTimeout=25 $RemoteHost "bash /tmp/ebz-remote.sh; ec=`$?; rm -f /tmp/ebz-remote.sh; exit `$ec"
    if ($LASTEXITCODE -ne 0) { throw "Comando remoto falló (exit $LASTEXITCODE)" }
  } finally {
    Remove-Item -Force $localSh -ErrorAction SilentlyContinue
  }
}

Write-Host "== Preflight SSH ==" -ForegroundColor Cyan
Invoke-Remote @"
set -e
echo HOST=`$(hostname)
# Redeploy-safe: 8090 may already belong to ia-bot-trading-dashboard
if ss -tlnp 2>/dev/null | grep -q ':8090'; then
  if docker ps --format '{{.Names}}' | grep -q 'ia-bot-trading-dashboard'; then
    echo '8090 owned by ia-bot-trading-dashboard — redeploy OK'
  else
    echo 'ERROR: puerto 8090 en uso por otro proceso'
    ss -tlnp | grep ':8090' || true
    exit 2
  fi
else
  echo '8090 libre OK'
fi
echo '--- baseline consultate/evs ---'
docker ps --format '{{.Names}} {{.Status}}' | grep -E 'consultate-|evs-' || echo '(ninguno listado)'
mkdir -p '$RemoteDir' '$RemoteDir/data/market_history'
"@

Write-Host "== Sync código ==" -ForegroundColor Cyan
$tmp = Join-Path $env:TEMP ("ia-bot-trading-sync-" + [guid]::NewGuid().ToString("N") + ".tar")
try {
  Push-Location $RepoRoot
  $tarArgs = @(
    "-cf", $tmp,
    "--exclude=.git",
    "--exclude=backups",
    "--exclude=node_modules",
    "--exclude=frontend/node_modules",
    "--exclude=frontend/dist",
    "--exclude=.env",
    "--exclude=docs/screenshots",
    "--exclude=__pycache__",
    "backend", "frontend", "deploy", "docs", "scripts", "data", "compose.yaml", ".env.example"
  )
  & tar @tarArgs
  if ($LASTEXITCODE -ne 0 -or -not (Test-Path $tmp)) { throw "tar local falló" }
  scp -o BatchMode=yes $tmp "${RemoteHost}:/tmp/ia-bot-trading-sync.tar"
  if ($LASTEXITCODE -ne 0) { throw "scp falló" }
  Invoke-Remote "mkdir -p '$RemoteDir' && tar -xf /tmp/ia-bot-trading-sync.tar -C '$RemoteDir' && rm -f /tmp/ia-bot-trading-sync.tar && mkdir -p '$RemoteDir/data/market_history'"
} finally {
  Pop-Location -ErrorAction SilentlyContinue
  if (Test-Path $tmp) { Remove-Item -Force $tmp -ErrorAction SilentlyContinue }
}

Write-Host "== Asegurar .env en servidor ==" -ForegroundColor Cyan
Invoke-Remote @"
set -e
cd '$RemoteDir'
if [ ! -f .env ]; then
  cp deploy/ebz/.env.ebz.example .env
  DB=`$(openssl rand -hex 24)
  TOK=`$(openssl rand -hex 24)
  sed -i "s/^DB_PASSWORD=.*/DB_PASSWORD=`$DB/" .env
  sed -i "s/^LAB_CONTROL_TOKEN=.*/LAB_CONTROL_TOKEN=`$TOK/" .env
  echo 'Generado .env nuevo con secretos aleatorios (no se muestran).'
else
  echo '.env ya existe; se conserva.'
fi
mkdir -p data/market_history
test -f deploy/ebz/docker-compose.yml
"@

if (-not $SkipBuild) {
  Write-Host "== docker compose up -d --build (solo ia-bot-trading) ==" -ForegroundColor Cyan
  $commit = (git -C $RepoRoot rev-parse HEAD).Trim()
  Invoke-Remote @"
set -e
cd '$RemoteDir'
# Record deploy commit without printing secrets
if grep -q '^DEPLOY_GIT_COMMIT=' .env; then
  sed -i "s/^DEPLOY_GIT_COMMIT=.*/DEPLOY_GIT_COMMIT=$commit/" .env
else
  echo "DEPLOY_GIT_COMMIT=$commit" >> .env
fi
docker compose -p ia-bot-trading -f $ComposeRel --env-file .env up -d --build
# Refresh dashboard nginx after API recreate (stale Docker DNS → 502)
docker compose -p ia-bot-trading -f $ComposeRel --env-file .env restart dashboard || true
sleep 3
# Persist deploy meta inside paper DB (best-effort)
docker compose -p ia-bot-trading -f $ComposeRel --env-file .env exec -T db \
  psql -U paper -d paper -c "CREATE TABLE IF NOT EXISTS deploy_meta(id INTEGER PRIMARY KEY CHECK (id=1), git_commit TEXT, deployed_at TIMESTAMPTZ, notes TEXT, updated_at TIMESTAMPTZ DEFAULT NOW()); INSERT INTO deploy_meta(id, git_commit, deployed_at, notes) VALUES (1, '$commit', NOW(), 'deploy_trading_ebz') ON CONFLICT (id) DO UPDATE SET git_commit=EXCLUDED.git_commit, deployed_at=EXCLUDED.deployed_at, notes=EXCLUDED.notes, updated_at=NOW();" \
  || echo 'deploy_meta update skipped'
# Safety: never touch foreign stacks
docker ps --format '{{.Names}} {{.Status}}' | grep -E 'consultate-|evs-' || true
"@
}

Write-Host "== Postflight ==" -ForegroundColor Cyan
Invoke-Remote @"
set -e
cd '$RemoteDir'
COMPOSE='docker compose -p ia-bot-trading -f $ComposeRel --env-file .env'
echo '--- ia-bot-trading ---'
`$COMPOSE ps
echo '--- consultate/evs intactos ---'
docker ps --format '{{.Names}} {{.Status}}' | grep -E 'consultate-|evs-' || true
echo '--- http dashboard ---'
code=`$(curl -sS -o /dev/null -w '%{http_code}' --max-time 20 http://127.0.0.1:8090/ || echo fail)
echo dashboard_http=`$code
echo '--- system mode ---'
curl -sS --max-time 25 http://127.0.0.1:8090/api/system 2>/dev/null | tr ',' '\n' | grep -E 'mode|PAPER|checked_at' | head -10 || true
echo '--- demo/active status ---'
`$COMPOSE exec -T db psql -U paper -d paper -tAc "SELECT 'demo='||COALESCE(status,'?') FROM demo_state WHERE id=1;" 2>/dev/null || echo 'demo_state pending'
`$COMPOSE exec -T db psql -U paper -d paper -tAc "SELECT 'active='||COALESCE(status,'?') FROM active_state WHERE id=1;" 2>/dev/null || echo 'active_state pending'
"@

Write-Host ""
Write-Host "Listo. Dashboard LAN:  http://192.168.1.12:8090" -ForegroundColor Green
Write-Host "Tailscale: IP del host ebz en puerto 8090" -ForegroundColor Green
Write-Host "Rollback: ssh $RemoteHost `"cd $RemoteDir && docker compose -p ia-bot-trading -f $ComposeRel down`"" -ForegroundColor Yellow
Write-Host "(Nunca uses down -v / prune en este servidor compartido.)" -ForegroundColor Yellow
