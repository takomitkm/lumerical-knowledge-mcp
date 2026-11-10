param(
  [Parameter(Mandatory = $true, Position = 0)][string]$Query,
  [int]$TopK = 8,
  [string]$Base = 'http://RAG_HOST:8900',
  [string]$Collection = 'lumerical',
  [string]$Token = ''
)
<#
  rag-query.ps1  — 查询 102 上的 Lumerical RAG 服务。
  用法:
    .\rag-query.ps1 "how to set mesh accuracy in FDTD" -TopK 8
    .\rag-query.ps1 "band structure sweep" -Base http://127.0.0.1:8900   # 校机经 SSH 隧道
  Token 取值顺序: -Token 参数 > 环境变量 RAG_TOKEN > 文件 %USERPROFILE%\.rag\token
#>
$ErrorActionPreference = 'Stop'
if (-not $Token) { $Token = $env:RAG_TOKEN }
if (-not $Token) {
  $tf = Join-Path $env:USERPROFILE '.rag\token'
  if (Test-Path $tf) { $Token = (Get-Content $tf -Raw).Trim() }
}
if (-not $Token) { Write-Error 'no token: pass -Token, set RAG_TOKEN, or put it in ~/.rag/token'; exit 1 }

$u = "$Base/search?q=$([uri]::EscapeDataString($Query))&top_k=$TopK&collection=$Collection"
$r = Invoke-RestMethod -Uri $u -Headers @{ Authorization = "Bearer $Token" } -TimeoutSec 90

Write-Host ("Query: {0}   ({1} hits, collection={2})" -f $r.query, $r.count, $r.collection) -ForegroundColor Cyan
$i = 0
foreach ($h in $r.results) {
  $i++
  $m = $h.meta
  $sc = if ($null -ne $h.score) { '{0:N4}' -f $h.score } else { 'n/a' }
  Write-Host ("`n[$i] rerank={0}  rrf={1}  vec={2}  bm25={3}" -f $sc, $h.rrf, $h.vscore, $h.bscore) -ForegroundColor Yellow
  Write-Host ("  " + $m.breadcrumb) -ForegroundColor Green
  if ($m.url) { Write-Host ("  " + $m.url) -ForegroundColor DarkGray }
  $t = ($h.text -replace "`r", '')
  if ($t.Length -gt 600) { $t = $t.Substring(0, 600) + ' …' }
  Write-Host ("  " + ($t -replace "`n", "`n  "))
}
