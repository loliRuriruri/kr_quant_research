[CmdletBinding()]
param(
    [int]$Port = 8790
)

$ErrorActionPreference = 'SilentlyContinue'

function Get-ListenerProcessIds {
    return @(Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue |
        Where-Object { $_.State -eq 'Listen' -and $_.OwningProcess -gt 0 } |
        Select-Object -ExpandProperty OwningProcess -Unique)
}

function Get-QuantServerProcessIds {
    $ids = New-Object System.Collections.Generic.List[int]
    foreach ($processId in @(Get-ListenerProcessIds)) {
        $ids.Add([int]$processId)
        $proc = Get-CimInstance Win32_Process -Filter "ProcessId=$processId" -ErrorAction SilentlyContinue
        if (-not $proc) { continue }
        $parent = Get-CimInstance Win32_Process -Filter "ProcessId=$($proc.ParentProcessId)" -ErrorAction SilentlyContinue
        if ($parent -and $parent.CommandLine -match 'kr_quant\.web\.app') {
            $ids.Add([int]$parent.ProcessId)
        }
        Get-CimInstance Win32_Process -Filter "ParentProcessId=$processId" -ErrorAction SilentlyContinue |
            Where-Object { $_.CommandLine -match 'kr_quant\.web\.app' } |
            ForEach-Object { $ids.Add([int]$_.ProcessId) }
    }
    return @($ids | Select-Object -Unique)
}

$processIds = @(Get-QuantServerProcessIds)
$stopped = 0
foreach ($processId in $processIds) {
    if ($processId -gt 0) {
        Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue
        $stopped++
    }
}
if ($stopped -gt 0) {
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
        Write-Error "포트 ${Port}의 서버 리스너가 아직 종료되지 않았습니다: $($detail -join '; ')"
        exit 1
    }
    Write-Host "포트 ${Port}의 서버 프로세스를 정상 종료했습니다." -ForegroundColor Green
} else {
    Write-Host "실행 중인 서버 프로세스가 없습니다." -ForegroundColor Yellow
}
exit 0
