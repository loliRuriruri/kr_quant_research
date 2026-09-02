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

function Test-QuantListen {
    return [bool]@(Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue |
        Where-Object { $_.State -eq 'Listen' -and $_.OwningProcess -gt 0 })
}

function Test-QuantServer {
    try {
        # Freshness reads prices.parquet; a 2s probe times out on a live server.
        $res = Invoke-RestMethod -Uri "${Url}api/status" -TimeoutSec 15
        return $null -ne $res
    }
    catch {
        return $false
    }
}

if (-not (Test-QuantServer)) {
    if (Test-QuantListen) {
        $listeners = @(Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue |
            Where-Object { $_.State -eq 'Listen' -and $_.OwningProcess -gt 0 } |
            Select-Object -ExpandProperty OwningProcess -Unique)
        foreach ($pidNum in $listeners) {
            $proc = Get-CimInstance Win32_Process -Filter "ProcessId=$pidNum" -ErrorAction SilentlyContinue
            if ($proc -and $proc.CommandLine -notmatch 'kr_quant' -and $proc.ExecutablePath -notmatch 'kr_quant') {
                throw "포트 ${Port}를 다른 프로그램(PID ${pidNum}: $($proc.ExecutablePath))이 점유하고 있습니다. 충돌 방지를 위해 서버를 실행하지 않습니다."
            }
        }
    }

    $stdout = Join-Path $LogsDir 'web.stdout.log'
    $stderr = Join-Path $LogsDir 'web.stderr.log'
    $launcher = Join-Path $RuntimeDir 'start-web.cmd'

    if (-not (Test-QuantListen)) {
        foreach ($path in @($stdout, $stderr)) {
            if (Test-Path $path) {
                try { Move-Item -LiteralPath $path -Destination "$path.prev" -Force } catch { }
            }
        }

        # Detach via cmd so the server outlives this PowerShell process.
        # Direct Start-Process python with redirected stdio dies when the bat exits.
        $lines = @(
            '@echo off'
            'chcp 65001 >nul'
            "cd /d `"$ProjectRoot`""
            "`"$PythonExe`" -m kr_quant.web.app >> `"$stdout`" 2>> `"$stderr`""
        )
        Set-Content -LiteralPath $launcher -Value $lines -Encoding ASCII

        # Win32_Process.Create starts outside this shell's Job Object, so the
        # server keeps running after Start-KR-Quant.bat (and agent commands) exit.
        $created = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{
            CommandLine = "cmd.exe /c `"$launcher`""
            CurrentDirectory = $ProjectRoot
        }
        if ([int]$created.ReturnValue -ne 0) {
            throw "서버 프로세스 생성 실패 (Win32 code $($created.ReturnValue))."
        }
    }

    $ready = $false
    $deadline = (Get-Date).AddSeconds(60)
    while ((Get-Date) -lt $deadline) {
        if (Test-QuantServer) {
            $ready = $true
            break
        }
        Start-Sleep -Milliseconds 400
    }
    if ($ready) {
        Start-Sleep -Seconds 1
        if (-not (Test-QuantListen)) {
            $ready = $false
        }
    }
    if (-not $ready) {
        $listenNote = if (Test-QuantListen) {
            "포트 ${Port}는 LISTEN 상태입니다. /api/status가 15초 안에 응답하지 않았습니다."
        } else {
            "포트 ${Port}에 리스너가 없습니다. 기동 직후 종료됐을 수 있습니다."
        }
        throw "서버 실행 시간 초과. $listenNote 로그 확인: $stderr"
    }
}

if (-not $NoBrowser) {
    Start-Process $Url
}
