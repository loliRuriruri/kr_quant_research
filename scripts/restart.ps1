[CmdletBinding()]
param(
    [int]$Port = 8790,
    [switch]$NoBrowser
)

$ErrorActionPreference = 'Stop'

function Get-ListenerProcessIds {
    return @(Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue |
        Where-Object { $_.State -eq 'Listen' -and $_.OwningProcess -gt 0 } |
        Select-Object -ExpandProperty OwningProcess -Unique)
}

try {
    # Start is intentionally a clean restart: stale processes from a previous
    # run must not make the user unknowingly reuse an old server/data state.
    # Only LISTEN sockets own the server port. ESTABLISHED/TIME_WAIT rows may
    # linger after the process exits and must not be treated as a live server.
    $processIds = @(Get-ListenerProcessIds)
    foreach ($processId in $processIds) {
        if (Get-Process -Id $processId -ErrorAction SilentlyContinue) {
            try {
                Stop-Process -Id $processId -Force -ErrorAction Stop
            }
            catch {
                throw "포트 ${Port} 리스너(PID ${processId}) 종료 실패: $($_.Exception.Message)"
            }
        }
    }

    $remaining = @(Get-ListenerProcessIds)
    for ($attempt = 0; $remaining.Count -gt 0 -and $attempt -lt 20; $attempt++) {
        Start-Sleep -Milliseconds 250
        $remaining = @(Get-ListenerProcessIds)
    }

    if ($remaining.Count -gt 0) {
        throw "포트 ${Port}의 기존 리스너(PID $($remaining -join ', '))를 5초 안에 종료하지 못했습니다."
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
