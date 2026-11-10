# Capture a v241 capability snapshot on this machine.
# Requires an open, licensed Lumerical CAD session for ?getcommands;
# without one, everything is recorded as not_run/unknown (honest pending).
# Usage: powershell -NoProfile -ExecutionPolicy Bypass -File capture-capability.ps1
$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$stamp = (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')

Write-Host '== Lumerical v241 capability capture =='
$cad = Get-Process -Name 'fdtd-solutions' -ErrorAction SilentlyContinue
if (-not $cad) {
    Write-Warning 'No running fdtd-solutions (CAD) process found. Open Lumerical once, then re-run.'
    Write-Host 'Recording probes as not_run; commands.json stays empty (unknown state).'
} else {
    Write-Host 'Found fdtd-solutions process (PID' $cad.Id ').'
    Write-Host @'
MANUAL STEP (one-time, ~20 seconds):
  1. In the Lumerical window: press the Script Prompt button (or View -> Script Prompt).
  2. Type:   ?getcommands;
  3. Select the whole output, copy it, paste into:  getcommands_raw.txt  (next to this script).
  4. Press Enter here to continue.
'@
    Read-Host 'Press Enter after saving getcommands_raw.txt' | Out-Null
}

$raw = Join-Path $here 'getcommands_raw.txt'
if (Test-Path $raw) {
    $lines = Get-Content $raw | Where-Object { $_.Trim() -ne '' }
    $symbols = @()
    foreach ($l in $lines) {
        foreach ($tok in ($l -split '[,\s]+')) {
            $t = $tok.Trim()
            if ($t -match '^[A-Za-z_][A-Za-z0-9_]*$') { $symbols += $t }
        }
    }
    $symbols = $symbols | Sort-Object -Unique
    $cmds = Get-Content (Join-Path $here 'commands.json') -Raw | ConvertFrom-Json
    $cmds.captured_at = $stamp
    $cmds.symbols = foreach ($s in $symbols) {
        [pscustomobject]@{ name = $s; symbol_type = 'command'; presence = 'present'
                           evidence_method = 'getcommands'; signature_status = 'not_tested'
                           notes = 'Command presence only; does not establish signatures or semantics.' }
    }
    $cmds | ConvertTo-Json -Depth 6 | Set-Content (Join-Path $here 'commands.json') -Encoding UTF8
    Write-Host ('commands.json: ' + $symbols.Count + ' symbols')
} else {
    Write-Warning 'getcommands_raw.txt not found - commands.json left empty (unknown).'
}

$envj = Get-Content (Join-Path $here 'environment.json') -Raw | ConvertFrom-Json
$envj.captured_at = $stamp
$envj.platform = [System.Environment]::OSVersion.VersionString
$envj | ConvertTo-Json -Depth 5 | Set-Content (Join-Path $here 'environment.json') -Encoding UTF8

$idx = Get-Content (Join-Path $here 'capability-snapshot.json') -Raw | ConvertFrom-Json
$idx.captured_at = $stamp
if (Test-Path $raw) {
    $bytes = [System.IO.File]::ReadAllBytes($raw)
    $sha = [System.Security.Cryptography.SHA256]::Create()
    $idx.commands_sha256 = ([BitConverter]::ToString($sha.ComputeHash($bytes)) -replace '-','').ToLower()
}
$idx | ConvertTo-Json -Depth 5 | Set-Content (Join-Path $here 'capability-snapshot.json') -Encoding UTF8
Write-Host 'Snapshot files ready. Zip this folder and bring it back to the laptop.'
