param(
    [int]$Port = 8790,
    [switch]$NoBrowser
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$PythonExe = Join-Path $ProjectRoot '.venv\Scripts\python.exe'
$RuntimeDir = Join-Path $ProjectRoot '.runtime'
$LogsDir = Join-Path $ProjectRoot 'logs'
$Url = "http://127.0.0.1:$Port/"

if (-not (Test-Path $PythonExe)) {
    throw "가상환경 파이썬(.venv)이 없습니다: $PythonExe"
}

New-Item -ItemType Directory -Path $RuntimeDir -Force | Out-Null
New-Item -ItemType Directory -Path $LogsDir -Force | Out-Null

function Test-QuantServer {
    try {
        $res = Invoke-RestMethod -Uri "${Url}api/status" -TimeoutSec 2
        return $res.freshness -ne $null -or $res.quality -ne $null
    }
    catch {
        return $false
    }
}

if (-not (Test-QuantServer)) {
    $stdout = Join-Path $LogsDir 'web.stdout.log'
    $stderr = Join-Path $LogsDir 'web.stderr.log'
    
    Start-Process -FilePath $PythonExe `
        -ArgumentList @("-m", "kr_quant.web.app") `
        -WorkingDirectory $ProjectRoot `
        -WindowStyle Hidden `
        -RedirectStandardOutput $stdout `
        -RedirectStandardError $stderr | Out-Null

    $ready = $false
    for ($attempt = 0; $attempt -lt 40; $attempt++) {
        Start-Sleep -Milliseconds 250
        if (Test-QuantServer) {
            $ready = $true
            break
        }
    }
    if (-not $ready) {
        throw "서버 실행 시간 초과. 로그 확인: $stderr"
    }
}

if (-not $NoBrowser) {
    Start-Process $Url
}
