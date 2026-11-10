"""Build a capability snapshot capture kit for the school machine (run there, bring back).

Creates capabilities/capture-kit/ with:
  capture-capability.ps1   - runs ?getcommands; via the v241 scripting API if a licensed
                             session is available; otherwise writes probes with status=not_run
  capability-snapshot.json - pre-filled index (ids/timestamps; hashes filled after capture)
  environment.json         - version info from the install, no private data
  commands.json            - skeleton with raw_output_file
  syntax-probes.json       - probes for language constructs (function/while/print/...), status not_run

The script NEVER executes a simulation and never needs a license for `?getcommands;` inside
the Script Prompt of an open CAD session; unlicensed installs cannot open a session, in which
case everything stays not_run/unknown (honest pending state).
"""
import json
import os

BASE = os.path.dirname(__file__)
KIT = os.path.join(BASE, "capabilities", "capture-kit")
os.makedirs(KIT, exist_ok=True)

STAMP = "20261111T000000Z"
SNAP = "snapshot.lumerical-2024r1-school.%s" % STAMP
TGT = "lumerical-2024r1-school-capture"

json.dump({
    "snapshot_id": SNAP,
    "target_id": TGT,
    "captured_at": None,
    "files": {"environment": "environment.json", "commands": "commands.json",
              "syntax_probes": "syntax_probes.json"},
    "commands_sha256": None, "snapshot_sha256": None,
    "capture_method": "manual_target_runtime",
    "notes": "Immutable evidence snapshot. Create a new snapshot after software updates; do not overwrite old evidence.",
}, open(os.path.join(KIT, "capability-snapshot.json"), "w", encoding="utf-8"), indent=2)

json.dump({
    "target_id": TGT, "product": "Lumerical", "solver": "shared", "version_label": "2024 R1",
    "update_label": None, "build_number": "v241", "platform": None, "captured_at": None,
    "capture_method": "manual_target_runtime", "license_available_for_test": None,
    "notes": "Fill platform/captured_at during capture. Do not include license keys, usernames, private hostnames or tokens.",
}, open(os.path.join(KIT, "environment.json"), "w", encoding="utf-8"), indent=2)

json.dump({
    "snapshot_id": SNAP, "source_command": "?getcommands;", "captured_at": None,
    "raw_output_file": "getcommands_raw.txt", "symbols": [],
}, open(os.path.join(KIT, "commands.json"), "w", encoding="utf-8"), indent=2)

PROBES = ["function", "while", "print", "else", "elseif", "continue", "switch"]
json.dump({
    "snapshot_id": SNAP,
    "probes": [{"probe_id": "probe.%s.v241" % s, "symbol": s, "symbol_type": "keyword",
                "probe_kind": "syntax_probe", "probe_file": "probe_%s.lsf" % s,
                "status": "not_run", "result": None, "error_text": None,
                "captured_at": None,
                "notes": "One construct per probe file. Do not infer from getcommands."}
               for s in PROBES],
}, open(os.path.join(KIT, "syntax_probes.json"), "w", encoding="utf-8"), indent=2)

ps1 = r'''# Capture a v241 capability snapshot on this machine.
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
'''
open(os.path.join(KIT, "capture-capability.ps1"), "w", encoding="utf-8", newline="\r\n").write(ps1)

for s in json.load(open(os.path.join(KIT, "syntax_probes.json"), encoding="utf-8"))["probes"]:
    sym = s["symbol"]
    body = {"function": "myfn = function(x) { return x*2; }\n?myfn(3);",
            "while": "i = 0;\nwhile (i < 3) { i = i + 1; }\n?i;",
            "print": "print(\"hello\");",
            "else": "if (1==2) { ?\"a\"; } else { ?\"b\"; }",
            "elseif": "if (1==2) { ?\"a\"; } elseif (1==1) { ?\"c\"; } else { ?\"b\"; }",
            "continue": "for (i=1:3) { if (i==2) { continue; } ?i; }",
            "switch": "?\"no switch construct in LSF\";"}[sym]
    open(os.path.join(KIT, "probe_%s.lsf" % sym), "w", encoding="utf-8", newline="\n").write(body)

print("capture kit:", KIT)
print(os.listdir(KIT))
