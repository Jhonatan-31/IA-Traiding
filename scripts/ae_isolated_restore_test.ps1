# AE9 — restauración aislada de un dump paper (NO toca Postgres operativo).
# Usage:
#   powershell -ExecutionPolicy Bypass -File scripts/ae_isolated_restore_test.ps1 -DumpPath backups\paper_pre_etapa_ae_*.dump

param(
  [Parameter(Mandatory = $true)][string]$DumpPath,
  [string]$Image = "postgres:16-alpine"
)

$ErrorActionPreference = "Stop"
if (-not (Test-Path $DumpPath)) { throw "Dump no encontrado: $DumpPath" }

$name = "ia-bot-ae-restore-test-" + [guid]::NewGuid().ToString("N").Substring(0, 8)
$sw = [Diagnostics.Stopwatch]::StartNew()
Write-Host "Contenedor aislado: $name" -ForegroundColor Cyan

try {
  docker run -d --name $name -e POSTGRES_PASSWORD=ae_test -e POSTGRES_USER=paper -e POSTGRES_DB=paper $Image | Out-Null
  # wait ready
  $ok = $false
  for ($i = 0; $i -lt 30; $i++) {
    Start-Sleep -Seconds 2
    docker exec $name pg_isready -U paper -d paper 2>$null | Out-Null
    if ($LASTEXITCODE -eq 0) { $ok = $true; break }
  }
  if (-not $ok) { throw "Postgres aislado no listo" }

  docker cp $DumpPath "${name}:/tmp/restore.dump"
  $t0 = [Diagnostics.Stopwatch]::StartNew()
  docker exec $name pg_restore -U paper -d paper --no-owner --role=paper /tmp/restore.dump
  # pg_restore may return non-zero with warnings; verify with query
  $t0.Stop()
  Write-Host ("restore_wall_ms=" + $t0.ElapsedMilliseconds)

  $tables = docker exec $name psql -U paper -d paper -tAc "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='public';"
  Write-Host "public_tables=$tables"
  $demo = docker exec $name psql -U paper -d paper -tAc "SELECT COALESCE((SELECT status FROM demo_state WHERE id=1),'missing');" 2>$null
  $active = docker exec $name psql -U paper -d paper -tAc "SELECT COALESCE((SELECT status FROM active_state WHERE id=1),'missing');" 2>$null
  Write-Host "demo_status=$demo active_status=$active"
  if ([int]$tables -lt 1) { throw "Restauración sin tablas" }
  $sw.Stop()
  Write-Host ("TOTAL_MS=" + $sw.ElapsedMilliseconds)
  Write-Host "RESTORE_ISOLATED_OK" -ForegroundColor Green
} finally {
  docker rm -f $name 2>$null | Out-Null
  Write-Host "Contenedor aislado eliminado (sin tocar volúmenes ia-bot-trading_*)." -ForegroundColor Yellow
}
