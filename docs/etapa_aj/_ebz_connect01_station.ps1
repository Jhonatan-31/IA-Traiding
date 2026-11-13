# EBZ-CONNECT-01 — diagnóstico estación (solo lectura). No modifica red/servicios.
$ErrorActionPreference = "Continue"
$outDir = Join-Path $PSScriptRoot "_evidence_ebz_connect01"
New-Item -ItemType Directory -Force -Path $outDir | Out-Null
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$log = Join-Path $outDir "station_$stamp.txt"

function W($m) { $m | Tee-Object -FilePath $log -Append }

W "=== EBZ-CONNECT-01 station $stamp ==="
W "UTC=$( [DateTime]::UtcNow.ToString('o') ) Local=$(Get-Date -Format o)"

W "`n--- ipconfig ---"
ipconfig /all 2>&1 | Tee-Object -FilePath $log -Append | Out-Null
# redact-ish summary only to console path via selective
Get-NetIPConfiguration | ForEach-Object {
  W ("IF={0} Alias={1} IPv4={2} GW={3} DNS={4}" -f $_.InterfaceIndex, $_.InterfaceAlias, (($_.IPv4Address | ForEach-Object Address) -join ','), (($_.IPv4DefaultGateway | ForEach-Object NextHop) -join ','), (($_.DNSServer.ServerAddresses) -join ','))
}

W "`n--- route (IPv4 active) ---"
Get-NetRoute -AddressFamily IPv4 -ErrorAction SilentlyContinue |
  Where-Object { $_.DestinationPrefix -in @('0.0.0.0/0','192.168.1.0/24','192.168.0.0/16','100.64.0.0/10') -or $_.DestinationPrefix -like '192.168.1.*' -or $_.DestinationPrefix -like '100.*' } |
  Select-Object DestinationPrefix,NextHop,InterfaceAlias,RouteMetric |
  Format-Table -AutoSize | Out-String | Tee-Object -FilePath $log -Append | ForEach-Object { W $_.TrimEnd() }

W "`n--- ARP sample ---"
arp -a 2>&1 | Select-String -Pattern "192\.168\.1\.|100\.107\.|Interfaz|Interface" | ForEach-Object { W $_.Line }

W "`n--- adapters ---"
Get-NetAdapter | Select-Object Name,Status,LinkSpeed,MacAddress | Format-Table -AutoSize | Out-String | Tee-Object -FilePath $log -Append | ForEach-Object { W $_.TrimEnd() }

W "`n--- VPN / tunnels ---"
Get-VpnConnection -ErrorAction SilentlyContinue | Select-Object Name,ConnectionStatus,ServerAddress | Format-List | Out-String | Tee-Object -FilePath $log -Append | ForEach-Object { W $_.TrimEnd() }
Get-NetAdapter | Where-Object { $_.InterfaceDescription -match 'VPN|TAP|TUN|WireGuard|OpenVPN|Tailscale|Wintun' -or $_.Name -match 'VPN|Tailscale|Wintun' } |
  Select-Object Name,Status,InterfaceDescription | Format-Table -AutoSize | Out-String | Tee-Object -FilePath $log -Append | ForEach-Object { W $_.TrimEnd() }

W "`n--- Test-NetConnection ---"
foreach ($t in @(
  @{H='192.168.1.1'; P=80},
  @{H='192.168.1.1'; P=53},
  @{H='192.168.1.12'; P=22},
  @{H='192.168.1.12'; P=8090},
  @{H='192.168.1.12'; P=443},
  @{H='192.168.1.12'; P=3080},
  @{H='192.168.1.12'; P=8088},
  @{H='100.107.168.61'; P=22},
  @{H='100.107.168.61'; P=8090},
  @{H='100.107.168.61'; P=443},
  @{H='8.8.8.8'; P=53},
  @{H='1.1.1.1'; P=443}
)) {
  try {
    $r = Test-NetConnection -ComputerName $t.H -Port $t.P -WarningAction SilentlyContinue
    W ("TNC {0}:{1} Ping={2} Tcp={3}" -f $t.H, $t.P, $r.PingSucceeded, $r.TcpTestSucceeded)
  } catch {
    W ("TNC {0}:{1} ERR {2}" -f $t.H, $t.P, $_.Exception.Message)
  }
}

W "`n--- Gateway reach ---"
$gw = (Get-NetIPConfiguration | Where-Object { $_.IPv4DefaultGateway } | Select-Object -First 1).IPv4DefaultGateway.NextHop
if ($gw) {
  W "GW=$gw"
  try { $rg = Test-NetConnection -ComputerName $gw -WarningAction SilentlyContinue; W ("GW Ping={0}" -f $rg.PingSucceeded) } catch { W "GW test err" }
}

W "`n--- DNS resolve ---"
foreach ($name in @('servidor-ebz','servidor-ebz.tail528f82.ts.net','google.com')) {
  try {
    $a = Resolve-DnsName $name -ErrorAction Stop | Select-Object -First 3 Name,Type,IPAddress
    $a | ForEach-Object { W ("DNS {0} -> {1} {2}" -f $name, $_.Type, $_.IPAddress) }
  } catch { W ("DNS {0} FAIL {1}" -f $name, $_.Exception.Message) }
}

W "`n--- Tailscale ---"
$ts = "$env:ProgramFiles\Tailscale\tailscale.exe"
if (Test-Path $ts) {
  & $ts version 2>&1 | ForEach-Object { W $_ }
  & $ts status 2>&1 | ForEach-Object { W $_ }
  & $ts netcheck 2>&1 | ForEach-Object { W $_ }
  & $ts ping -c 3 100.107.168.61 2>&1 | ForEach-Object { W $_ }
  & $ts ping --tsmp -c 2 100.107.168.61 2>&1 | ForEach-Object { W $_ }
  & $ts ping -c 2 100.84.201.34 2>&1 | ForEach-Object { W $_ }  # creo-server control peer
} else { W "tailscale.exe missing" }

W "`nLOG=$log"
W "=== DONE ==="
