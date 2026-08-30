[CmdletBinding()]
param(
    [int]$Port = 8790,
    [switch]$NoBrowser
)

$ErrorActionPreference = 'Stop'

try {
    # Start is intentionally a clean restart: stale processes from a previous
    # run must not make the user unknowingly reuse an old server/data state.
    $connections = @(Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue)
    $processIds = @($connections | Where-Object { $_.OwningProcess -gt 0 } |
        Select-Object -ExpandProperty OwningProcess -Unique)
    foreach ($processId in $processIds) {
        Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue
    }

    if ($processIds.Count -gt 0) {
        Start-Sleep -Milliseconds 500
    }

    $remaining = @(Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue |
        Where-Object { $_.OwningProcess -gt 0 })
    if ($remaining.Count -gt 0) {
        throw "포트 ${Port}의 기존 프로세스를 종료하지 못했습니다. 관리자 권한 또는 logs를 확인하세요."
    }

    $launchScript = Join-Path $PSScriptRoot 'launch.ps1'
    if (-not (Test-Path $launchScript)) {
        throw "런처 스크립트가 없습니다: $launchScript"
    }

    if ($NoBrowser) {
        & $launchScript -Port $Port -NoBrowser
    } else {
        & $launchScript -Port $Port
    }

    Write-Host "서버가 성공적으로 재시작되었습니다. (포트 $Port)" -ForegroundColor Green
    exit 0
}
catch {
    Write-Error $_
    exit 1
}
