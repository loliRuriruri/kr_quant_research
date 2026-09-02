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

function Get-QuantServerProcessIds {
    $ids = New-Object System.Collections.Generic.List[int]
    foreach ($processId in @(Get-ListenerProcessIds)) {
        $proc = Get-CimInstance Win32_Process -Filter "ProcessId=$processId" -ErrorAction SilentlyContinue
        if (-not $proc) { continue }
        $parent = Get-CimInstance Win32_Process -Filter "ProcessId=$($proc.ParentProcessId)" -ErrorAction SilentlyContinue

        $isQuant = ($proc.CommandLine -match 'kr_quant' -or 
                    $proc.ExecutablePath -match 'kr_quant' -or 
                    ($parent -and $parent.CommandLine -match 'kr_quant'))

        if ($isQuant) {
            $ids.Add([int]$processId)
            if ($parent -and $parent.CommandLine -match 'kr_quant\.web\.app') {
                $ids.Add([int]$parent.ProcessId)
            }
            Get-CimInstance Win32_Process -Filter "ParentProcessId=$processId" -ErrorAction SilentlyContinue |
                Where-Object { $_.CommandLine -match 'kr_quant\.web\.app' } |
                ForEach-Object { $ids.Add([int]$_.ProcessId) }
        } else {
            throw "포트 ${Port}가 다른 프로그램(PID ${processId}: $($proc.ExecutablePath))에 의해 사용 중입니다. 무관한 프로세스 보호를 위해 서버를 시작하지 않습니다."
        }
    }
    return @($ids | Select-Object -Unique)
}

try {
    # Start is intentionally a clean restart: stale processes from a previous
    # run must not make the user unknowingly reuse an old server/data state.
    # Only LISTEN sockets own the server port. ESTABLISHED/TIME_WAIT rows may
    # linger after the process exits and must not be treated as a live server.
    # uvicorn may listen in a child python; stop the kr_quant parent too.
    $processIds = @(Get-QuantServerProcessIds)
    foreach ($processId in $processIds) {
        if (Get-Process -Id $processId -ErrorAction SilentlyContinue) {
            try {
                Stop-Process -Id $processId -Force -ErrorAction Stop
            }
            catch {
                throw "포트 ${Port} 프로세스(PID ${processId}) 종료 실패: $($_.Exception.Message)"
            }
        }
    }

    $remaining = @(Get-ListenerProcessIds)
    for ($attempt = 0; $remaining.Count -gt 0 -and $attempt -lt 20; $attempt++) {
        Start-Sleep -Milliseconds 250
        $remaining = @(Get-ListenerProcessIds)
    }

    if ($remaining.Count -gt 0) {
        $detail = foreach ($processId in $remaining) {
            $proc = Get-CimInstance Win32_Process -Filter "ProcessId=$processId" -ErrorAction SilentlyContinue
            "PID $processId $($proc.ExecutablePath)"
        }
        throw "포트 ${Port}의 기존 리스너를 5초 안에 종료하지 못했습니다: $($detail -join '; '). 무관한 프로세스는 종료하지 않습니다."
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
