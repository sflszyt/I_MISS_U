# ============================================================
# start_services.ps1
#
# Purpose:  Idempotently start (default), stop (-Stop), or check
#           (-Status) the five services that power the digital
#           memorial site.  Designed to run unattended after a
#           Windows reboot so the widower sees his wife's site
#           when he opens the browser in the morning.
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File scripts\start_services.ps1
#   powershell -ExecutionPolicy Bypass -File scripts\start_services.ps1 -Status
#   powershell -ExecutionPolicy Bypass -File scripts\start_services.ps1 -Stop
#   powershell -ExecutionPolicy Bypass -File scripts\start_services.ps1 -SkipTunnel
#   powershell -ExecutionPolicy Bypass -File scripts\start_services.ps1 -Quiet
#
# Exit codes:
#   0  All required services are up (start mode) or status check completed
#   1  At least one service failed to start or timed out (start mode)
#   2  Precondition check failed (start mode)
#   3  Another instance is already running (mutex timeout)
# ============================================================

param(
    [switch]$Status,
    [switch]$Stop,
    [switch]$SkipTunnel,
    [switch]$Quiet
)

$ErrorActionPreference = 'Stop'

# ------------------------------------------------------------
# Configuration - edit paths here if the layout changes
# ------------------------------------------------------------
$RepoRoot      = 'C:\Users\justin\Documents\I_MISS_U'
$VenvPython    = 'C:\Users\justin\venvs\cosyvoice\Scripts\python.exe'
$SysPython     = 'C:\Users\justin\AppData\Local\Programs\Python\Python310\python.exe'
$Cloudflared   = 'C:\Program Files (x86)\cloudflared\cloudflared.exe'
$TokensFile    = 'C:\Users\justin\Documents\I_MISS_U\people\mama_for_father\config\tokens.env'
$TunnelName    = 'imissu-father'
$CloudflaredConfigDir = 'C:\Users\justin'
$CloudflaredConfigFile = 'C:\Users\justin\.cloudflared\config.yml'
$LogDir        = Join-Path $RepoRoot 'logs'
$RunLog        = Join-Path $LogDir 'start_services.log'
$MaxLogSets    = 10
$LogRetention  = 30  # not used, kept for clarity

# Site directories
$SonSiteDir    = Join-Path $RepoRoot 'people\mama\archive_out'
$DadSiteDir    = Join-Path $RepoRoot 'people\mama_for_father\site'

# Tool scripts
$StaticServer  = Join-Path $RepoRoot 'tools\static_server.py'
$TtsScript     = Join-Path $RepoRoot 'tools\tts_server.py'
$LlmProxyScript= Join-Path $RepoRoot 'tools\llm_proxy.py'

# Ports
$SonPort       = 8020
$DadPort       = 8021
$TtsPort       = 8022
$LlmPort       = 8023

# Timeouts (seconds)
$TtsTimeout    = 300
$DefaultTimeout = 30
$TunnelTimeout = 60
$PortReleaseTimeout = 15

# Mutex name and timeout (ms)
$GlobalMutexName = 'Global\ImissuStartServices'
$MutexTimeoutStart = 600000   # 10 minutes (another instance may be waiting for tts 300s)
$MutexTimeoutOther = 30000    # 30 seconds for -Status / -Stop

# ------------------------------------------------------------
# Global state
# ------------------------------------------------------------
$script:OkCount    = 0
$script:SkipCount  = 0
$script:FailCount  = 0
$script:AnyFailure = $false

# ------------------------------------------------------------
# Output helpers
# ------------------------------------------------------------
function Write-Log {
    param([string]$Message)
    try {
        $timestamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
        $line = "$timestamp $Message"
        if (-not (Test-Path $LogDir)) {
            New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
        }
        Add-Content -Path $RunLog -Value $line -Encoding utf8
    }
    catch {
        # Logging failure must never stop the main flow
        if (-not $Quiet) {
            Write-Output "[warn] log write failed: $($_.Exception.Message)"
        }
    }
}

function Write-Status {
    param([string]$ServiceName)
    if (-not $Quiet) {
        Write-Output $ServiceName
    }
    Write-Log $ServiceName
}

# ------------------------------------------------------------
# Port helpers (fast, no Test-NetConnection)
# ------------------------------------------------------------
function Test-PortListening {
    param([int]$Port)
    try {
        $conn = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
        return ($null -ne $conn)
    }
    catch {
        return $false
    }
}

# Wait for a port to be released
function Wait-PortReleased {
    param([int]$Port, [int]$TimeoutSeconds)
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        if (-not (Test-PortListening -Port $Port)) {
            return $true
        }
        Start-Sleep -Milliseconds 500
    }
    return (-not (Test-PortListening -Port $Port))
}

# ------------------------------------------------------------
# Process helpers - multiple patterns must ALL match
# ------------------------------------------------------------
function Get-MatchingProcesses {
    param(
        [string]$ProcessName,
        [string[]]$CommandLinePatterns
    )
    $all = Get-CimInstance Win32_Process -Filter "Name = '$ProcessName'" -ErrorAction SilentlyContinue
    $matched = @()
    foreach ($proc in $all) {
        if (-not $proc.CommandLine) {
            continue
        }
        $isMatch = $true
        foreach ($pattern in $CommandLinePatterns) {
            if (-not $proc.CommandLine.Contains($pattern)) {
                $isMatch = $false
                break
            }
        }
        if ($isMatch) {
            $matched += $proc
        }
    }
    # Use the comma unary operator to prevent PowerShell from unrolling a single-element array into a scalar
    return ,$matched
}

function Test-ServiceRunningByName {
    param([string]$ServiceName)
    switch ($ServiceName) {
        'son-site' {
            $pats = @($StaticServer, '--port 8020', $SonSiteDir)
            $procs = Get-MatchingProcesses -ProcessName 'python.exe' -CommandLinePatterns $pats
            return ($null -ne $procs -and $procs.Count -gt 0)
        }
        'dad-site' {
            $pats = @($StaticServer, '--port 8021', $DadSiteDir)
            $procs = Get-MatchingProcesses -ProcessName 'python.exe' -CommandLinePatterns $pats
            return ($null -ne $procs -and $procs.Count -gt 0)
        }
        'tts' {
            $pats = @($TtsScript)
            $procs = Get-MatchingProcesses -ProcessName 'python.exe' -CommandLinePatterns $pats
            return ($null -ne $procs -and $procs.Count -gt 0)
        }
        'llm-proxy' {
            $pats = @($LlmProxyScript)
            $procs = Get-MatchingProcesses -ProcessName 'python.exe' -CommandLinePatterns $pats
            return ($null -ne $procs -and $procs.Count -gt 0)
        }
        'tunnel' {
            $procs = Get-MatchingProcesses -ProcessName 'cloudflared.exe' -CommandLinePatterns @("tunnel run $TunnelName")
            return ($null -ne $procs -and $procs.Count -gt 0)
        }
    }
    return $false
}

function Test-TunnelRunning {
    $procs = Get-MatchingProcesses -ProcessName 'cloudflared.exe' -CommandLinePatterns @("tunnel run $TunnelName")
    return ($null -ne $procs -and $procs.Count -gt 0)
}

# Stop processes matching the exact patterns, including children
function Stop-MatchingProcessTree {
    param(
        [string]$ProcessName,
        [string[]]$CommandLinePatterns,
        [string]$DisplayName
    )
    $all = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue
    $matching = @()
    foreach ($proc in $all) {
        if ($proc.Name -eq $ProcessName -and $proc.CommandLine) {
            $isMatch = $true
            foreach ($pattern in $CommandLinePatterns) {
                if (-not $proc.CommandLine.Contains($pattern)) {
                    $isMatch = $false
                    break
                }
            }
            if ($isMatch) {
                # Also include any child processes (parent-child chain)
                $parentId = $proc.ProcessId
                # Find descendants recursively
                $toAdd = @($proc)
                $iterationLimit = 50
                $iterationCount = 0
                do {
                    $newFound = $false
                    $iterationCount++
                    if ($iterationCount -gt $iterationLimit) {
                        break
                    }
                    foreach ($candidate in $all) {
                        if ($candidate.ParentProcessId -in $toAdd.ProcessId -and $candidate.ProcessId -notin $toAdd.ProcessId -and $candidate.Name -like 'python*') {
                            $toAdd += $candidate
                            $newFound = $true
                        }
                    }
                } while ($newFound)
                $matching += $toAdd
            }
        }
    }
    # Deduplicate
    $matching = $matching | Sort-Object ProcessId -Unique

    foreach ($p in $matching) {
        try {
            Stop-Process -Id $p.ProcessId -Force -ErrorAction Stop
            Write-Output "[stop] $DisplayName killed pid $($p.ProcessId)"
            Write-Log "[stop] $DisplayName killed pid $($p.ProcessId)"
        }
        catch {
            Write-Output "[warn] $DisplayName failed to kill pid $($p.ProcessId): $($_.Exception.Message)"
            Write-Log "[warn] $DisplayName failed to kill pid $($p.ProcessId): $($_.Exception.Message)"
        }
    }
    return (@($matching).Count -gt 0)
}

# ------------------------------------------------------------
# Log rotation for a service - keep only the newest MaxLogSets
# ------------------------------------------------------------
function Rotate-ServiceLogs {
    param([string]$ServiceName)
    try {
        $pattern = "$ServiceName.*.out.log"
        $logs = Get-ChildItem -Path $LogDir -Filter $pattern -ErrorAction SilentlyContinue
        if ($logs) {
            $logs | Sort-Object LastWriteTime -Descending | Select-Object -Skip $MaxLogSets | Remove-Item -Force -ErrorAction SilentlyContinue
        }
        # Also clean err logs
        $patternErr = "$ServiceName.*.err.log"
        $logsErr = Get-ChildItem -Path $LogDir -Filter $patternErr -ErrorAction SilentlyContinue
        if ($logsErr) {
            $logsErr | Sort-Object LastWriteTime -Descending | Select-Object -Skip $MaxLogSets | Remove-Item -Force -ErrorAction SilentlyContinue
        }
    }
    catch {
        # silent - rotation failure must not block startup
    }
}

# ------------------------------------------------------------
# HTTP health check
# ------------------------------------------------------------
function Test-HttpHealthy {
    param([string]$Url, [int]$TimeoutSec = 3)
    try {
        $resp = Invoke-RestMethod -Uri $Url -TimeoutSec $TimeoutSec -ErrorAction Stop
        if ($resp.status -eq 'ok') {
            return $true
        }
        return $false
    }
    catch {
        return $false
    }
}

# Check if a service has a health endpoint that returns HTTP 200
function Test-ServiceHealthy {
    param(
        [string]$Name,
        [int]$Port
    )
    if ($Name -eq 'tts' -or $Name -eq 'llm-proxy') {
        return (Test-HttpHealthy -Url "http://127.0.0.1:$Port/health")
    }
    else {
        # Static sites - check root returns HTTP 200
        try {
            $resp = Invoke-WebRequest -Uri "http://127.0.0.1:$Port/" -TimeoutSec 3 -UseBasicParsing -ErrorAction Stop
            return ($resp.StatusCode -eq 200)
        }
        catch {
            return $false
        }
    }
}

# ------------------------------------------------------------
# Start a single service with readiness check
# ------------------------------------------------------------
function Start-PortService {
    param(
        [string]$Name,
        [string]$DisplayName,
        [int]$Port,
        [string]$ExePath,
        [string[]]$ArgumentList,
        [int]$TimeoutSeconds,
        [string]$WorkingDir,
        [string[]]$MatchPatterns,
        [string]$ProcessName = 'python.exe'
    )

    # Generate log file names with timestamp
    $timestamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    $stdoutFile = Join-Path $LogDir "$Name.$timestamp.out.log"
    $stderrFile = Join-Path $LogDir "$Name.$timestamp.err.log"

    # Clean old logs before starting (keep only latest MaxLogSets)
    Rotate-ServiceLogs -ServiceName $Name

    $isHealthy = $false
    $isListening = Test-PortListening -Port $Port
    if ($isListening) {
        # Port is already in use - verify health
        $matchingProcs = @(Get-MatchingProcesses -ProcessName $ProcessName -CommandLinePatterns $MatchPatterns)
        $isHealthy = Test-ServiceHealthy -Name $Name -Port $Port
        if ($isHealthy -and (@($matchingProcs).Count -gt 0)) {
            # Both health check and process match are satisfied
            Write-Output ("[skip] {0,-11} :{1,-5} already running (healthy)" -f $DisplayName, $Port)
            Write-Log "[skip] $Name :$Port already running (healthy)"
            $script:SkipCount++
            return
        }
        elseif (-not (@($matchingProcs).Count -gt 0)) {
            # Port is held but not by OUR matching process - fail closed, DO NOT KILL
            try {
                $owningProc = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction Stop | Select-Object -First 1
                if ($owningProc) {
                    Write-Output ("[FAIL] {0,-11} :{1,-5} port held by non-matching process (pid {2}) -- not started" -f $DisplayName, $Port, $owningProc.OwningProcess)
                    Write-Log "[FAIL] $Name :$Port port held by non-matching process (pid $($owningProc.OwningProcess)) -- not started"
                    $script:FailCount++
                    $script:AnyFailure = $true
                    return
                }
            }
            catch {
                Write-Output ("[FAIL] {0,-11} :{1,-5} port in use by unidentified process -- not started" -f $DisplayName, $Port)
                Write-Log "[FAIL] $Name :$Port port in use by unidentified process -- not started"
                $script:FailCount++
                $script:AnyFailure = $true
                return
            }
        }
        else {
            # Matching process exists but unhealthy - self-heal (this is OUR broken process)
            Write-Output ("[warn] {0,-11} :{1,-5} port in use but unhealthy -- restarting" -f $DisplayName, $Port)
            Write-Log "[warn] $Name port in use but unhealthy -- restarting"
            $hadProc = Stop-MatchingProcessTree -ProcessName $ProcessName -CommandLinePatterns $MatchPatterns -DisplayName $DisplayName
            if ($hadProc) {
                # Wait for port to be released
                if (-not (Wait-PortReleased -Port $Port -TimeoutSeconds $PortReleaseTimeout)) {
                    Write-Output ("[FAIL] {0,-11} :{1,-5} port not released after stopping unhealthy process" -f $DisplayName, $Port)
                    Write-Log "[FAIL] $Name :$Port port not released after stopping unhealthy process"
                    $script:FailCount++
                    $script:AnyFailure = $true
                    return
                }
            }
            else {
                # Should not normally happen - matching proc was found but kill failed
                Write-Output ("[FAIL] {0,-11} :{1,-5} could not stop unhealthy matching process -- not started" -f $DisplayName, $Port)
                Write-Log "[FAIL] $Name :$Port could not stop unhealthy matching process -- not started"
                $script:FailCount++
                $script:AnyFailure = $true
                return
            }
        }
    }

    # Executable existence check
    if (-not (Test-Path $ExePath)) {
        Write-Output ("[FAIL] {0,-11} :{1,-5} executable not found: {2}" -f $DisplayName, $Port, $ExePath)
        Write-Log "[FAIL] $Name :$Port executable not found: $ExePath"
        $script:FailCount++
        $script:AnyFailure = $true
        return
    }

    # Start the process
    $startTime = Get-Date
    $proc = $null
    try {
        $startArgs = @{
            FilePath               = $ExePath
            ArgumentList           = $ArgumentList
            PassThru               = $true
            WindowStyle            = 'Hidden'
            RedirectStandardOutput = $stdoutFile
            RedirectStandardError  = $stderrFile
        }
        if ($WorkingDir) {
            $startArgs.WorkingDirectory = $WorkingDir
        }
        $proc = Start-Process @startArgs
        Write-Log "[start] $Name launched pid=$($proc.Id)"
    }
    catch {
        Write-Output ("[FAIL] {0,-11} :{1,-5} failed to launch: {2}" -f $DisplayName, $Port, $_.Exception.Message)
        Write-Log "[FAIL] $Name :$Port failed to launch: $($_.Exception.Message)"
        $script:FailCount++
        $script:AnyFailure = $true
        return
    }

    # Poll for readiness
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    $ready = $false
    while ((Get-Date) -lt $deadline) {
        if (Test-PortListening -Port $Port) {
            $isHealthy = Test-ServiceHealthy -Name $Name -Port $Port
            if ($isHealthy) {
                $ready = $true
                break
            }
        }
        Start-Sleep -Seconds 2
    }

    $elapsed = ((Get-Date) - $startTime).TotalSeconds

    if ($ready) {
        # Find the actual pids using the explicit match patterns - verify our process is genuinely running
        # to avoid false success if an external service took the port and responded to health checks.
        $runningProcs = @(Get-MatchingProcesses -ProcessName $ProcessName -CommandLinePatterns $MatchPatterns)
        if (@($runningProcs).Count -gt 0) {
            $pidList = @()
            foreach ($rp in $runningProcs) {
                $pidList += $rp.ProcessId
            }
            $pidStr = " pid=$($pidList -join ',')"
            Write-Output ("[ ok ] {0,-11} :{1,-5} ready in {2:N1}s{3}" -f $DisplayName, $Port, $elapsed, $pidStr)
            Write-Log ("[ ok ] {0,-11} :{1,-5} ready in {2:N1}s{3}" -f $DisplayName, $Port, $elapsed, $pidStr)
            $script:OkCount++
        }
        else {
            # Healthy but our process is gone - likely another service took the port
            Write-Output ("[FAIL] {0,-11} :{1,-5} healthy but no matching process -- port taken by another service" -f $DisplayName, $Port)
            Write-Log "[FAIL] $Name :$Port healthy but no matching process -- port taken by another service"
            $script:FailCount++
            $script:AnyFailure = $true
            # Cleanup half-started process
            $wasKilled = Stop-MatchingProcessTree -ProcessName $ProcessName -CommandLinePatterns $MatchPatterns -DisplayName $DisplayName
            if ($wasKilled) {
                Write-Output ("[warn] {0,-11} cleaned up after false health check" -f $DisplayName)
                Write-Log "[warn] $Name cleaned up after false health check"
            }
            else {
                # Fallback: kill the process we launched
                if ($proc -and (Get-Process -Id $proc.Id -ErrorAction SilentlyContinue)) {
                    Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
                    Write-Output ("[warn] {0,-11} cleaned up after false health check (pid {1})" -f $DisplayName, $proc.Id)
                    Write-Log "[warn] $Name cleaned up after false health check (pid $($proc.Id))"
                }
            }
        }
    }
    else {
        # Timeout - record failure and clean up the half-started process
        Write-Output ("[FAIL] {0,-11} :{1,-5} not ready after {2}s -- see logs\{3}.err.log" -f $DisplayName, $Port, $TimeoutSeconds, $Name)
        Write-Log "[FAIL] $Name :$Port not ready after ${TimeoutSeconds}s -- see logs\$Name.err.log"
        $script:FailCount++
        $script:AnyFailure = $true
        # Cleanup half-started process
        $wasKilled = Stop-MatchingProcessTree -ProcessName $ProcessName -CommandLinePatterns $MatchPatterns -DisplayName $DisplayName
        if ($wasKilled) {
            Write-Output ("[warn] {0,-11} cleaned up after timeout" -f $DisplayName)
            Write-Log "[warn] $Name cleaned up after timeout"
        }
        else {
            # Fallback: kill the process we launched
            if ($proc -and (Get-Process -Id $proc.Id -ErrorAction SilentlyContinue)) {
                Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
                Write-Output ("[warn] {0,-11} cleaned up after timeout (pid {1})" -f $DisplayName, $proc.Id)
                Write-Log "[warn] $Name cleaned up after timeout (pid $($proc.Id))"
            }
        }
    }
}

# ------------------------------------------------------------
# Start tunnel service
# ------------------------------------------------------------
function Start-TunnelService {
    if ($SkipTunnel) {
        if (-not $Quiet) { Write-Output '[skip] tunnel            skipped (-SkipTunnel)' }
        Write-Log '[skip] tunnel            skipped (-SkipTunnel)'
        $script:SkipCount++
        return
    }

    # Always restart tunnel if a process is already running - historical logs cannot prove current health.
    # A stale log or a previously registered-but-now-disconnected process would otherwise cause a false success.
    if (Test-ServiceRunningByName -ServiceName 'tunnel') {
        Write-Output '[warn] tunnel            already running -- restarting to verify connection'
        Write-Log '[warn] tunnel            already running -- restarting to verify connection'
        $wasKilled = Stop-MatchingProcessTree -ProcessName 'cloudflared.exe' -CommandLinePatterns @("tunnel run $TunnelName") -DisplayName 'tunnel'
        Start-Sleep -Seconds 2
        # Continue to normal startup below
    }

    if (-not (Test-Path $Cloudflared)) {
        Write-Output '[FAIL] tunnel            executable not found'
        Write-Log '[FAIL] tunnel            executable not found'
        $script:FailCount++
        $script:AnyFailure = $true
        return
    }

    # Explicit config check
    if (-not (Test-Path $CloudflaredConfigFile)) {
        Write-Output "[FAIL] tunnel            config not found: $CloudflaredConfigFile"
        Write-Log "[FAIL] tunnel            config not found: $CloudflaredConfigFile"
        $script:FailCount++
        $script:AnyFailure = $true
        return
    }

    $timestamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    $stdoutFile = Join-Path $LogDir "tunnel.$timestamp.out.log"
    $stderrFile = Join-Path $LogDir "tunnel.$timestamp.err.log"

    # Rotate old tunnel logs
    Rotate-ServiceLogs -ServiceName 'tunnel'

    $startTime = Get-Date
    $proc = $null
    try {
        # --config 是全局标志，必须在 'tunnel' 之前。放在 'run <name>' 之后会被当成位置参数，
        # cloudflared 报 "tunnel run accepts only one argument"（2026-09-10 实测）。
        # 用法：cloudflared [global options] tunnel [tunnel options] run [run options] [TUNNEL]
        $proc = Start-Process -FilePath $Cloudflared `
            -ArgumentList @('--config', $CloudflaredConfigFile, 'tunnel', 'run', $TunnelName) `
            -WorkingDirectory $CloudflaredConfigDir `
            -PassThru -WindowStyle Hidden `
            -RedirectStandardOutput $stdoutFile `
            -RedirectStandardError $stderrFile
        Write-Log "[start] tunnel launched pid=$($proc.Id)"
    }
    catch {
        Write-Output ("[FAIL] tunnel            failed to launch: {0}" -f $_.Exception.Message)
        Write-Log ("[FAIL] tunnel            failed to launch: {0}" -f $_.Exception.Message)
        $script:FailCount++
        $script:AnyFailure = $true
        return
    }

    # Poll stderr log for "Registered tunnel connection"
    $deadline = (Get-Date).AddSeconds($TunnelTimeout)
    $registered = $false
    while ((Get-Date) -lt $deadline) {
        if (Test-Path $stderrFile) {
            try {
                $content = Get-Content $stderrFile -Raw -ErrorAction SilentlyContinue
                if ($content -and $content.ToLower().Contains('registered tunnel connection')) {
                    $registered = $true
                    break
                }
            }
            catch {
                # ignore - log may be locked
            }
        }
        Start-Sleep -Seconds 2
    }

    $elapsed = ((Get-Date) - $startTime).TotalSeconds

    # Additional check: process still alive
    $stillAlive = $false
    if ($registered) {
        try {
            $checkProc = Get-Process -Id $proc.Id -ErrorAction SilentlyContinue
            if ($checkProc) {
                $stillAlive = $true
            }
            else {
                $stillAlive = Test-TunnelRunning
            }
        }
        catch {
            $stillAlive = Test-TunnelRunning
        }
    }

    if ($registered -and $stillAlive) {
        $pidStr = " pid $($proc.Id)"
        Write-Output ("[ ok ] tunnel             started in {0:N1}s ($pidStr)" -f $elapsed)
        Write-Log ("[ ok ] tunnel             started in {0:N1}s ($pidStr)" -f $elapsed)
        $script:OkCount++
    }
    else {
        if (-not $registered) {
            Write-Output ("[FAIL] tunnel             not registered within {0}s -- see logs\tunnel.{1}.err.log" -f $TunnelTimeout, $timestamp)
            Write-Log ("[FAIL] tunnel             not registered within {0}s -- see logs\tunnel.{1}.err.log" -f $TunnelTimeout, $timestamp)
        }
        else {
            Write-Output '[FAIL] tunnel             process exited after registration -- see logs\tunnel.err.log'
            Write-Log '[FAIL] tunnel             process exited after registration -- see logs\tunnel.err.log'
        }
        $script:FailCount++
        $script:AnyFailure = $true
        # Cleanup half-started tunnel
        $wasKilled = Stop-MatchingProcessTree -ProcessName 'cloudflared.exe' -CommandLinePatterns @("tunnel run $TunnelName") -DisplayName 'tunnel'
        if ($wasKilled) {
            Write-Output '[warn] tunnel             cleaned up after timeout'
            Write-Log '[warn] tunnel             cleaned up after timeout'
        }
        elseif ($proc -and (Get-Process -Id $proc.Id -ErrorAction SilentlyContinue)) {
            Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
            Write-Output ('[warn] tunnel             cleaned up after timeout (pid {0})' -f $proc.Id)
            Write-Log ('[warn] tunnel             cleaned up after timeout (pid {0})' -f $proc.Id)
        }
    }
}

# ------------------------------------------------------------
# Stop a service by name with exact matching
# ------------------------------------------------------------
function Stop-ServiceByName {
    param(
        [string]$Name,
        [string]$DisplayName,
        [string]$ProcessName,
        [string[]]$CommandLinePatterns,
        [int]$Port
    )

    # Max rounds for the supplementary re-scan (1 initial + 2 retries = 3 total)
    $maxRounds = 3
    $round = 0
    $portStillHeld = $false

    $procs = Get-MatchingProcesses -ProcessName $ProcessName -CommandLinePatterns $CommandLinePatterns

    if ($null -eq $procs -or $procs.Count -eq 0) {
        # No matching process - check if port is still bound
        if ($Port -gt 0) {
            $portListening = Test-PortListening -Port $Port
            if ($portListening) {
                Write-Output "[warn] :$Port still in use after stop -- a process not started by this script may be holding it"
                Write-Log "[warn] :$Port still in use after stop -- a process not started by this script may be holding it"
            }
            else {
                Write-Output "[ ok ] $DisplayName stopped (was not running)"
                Write-Log "[ ok ] $DisplayName stopped (was not running)"
            }
        }
        else {
            Write-Output "[ ok ] $DisplayName stopped (was not running)"
            Write-Log "[ ok ] $DisplayName stopped (was not running)"
        }
        return
    }

    # Main stop loop with re-scan capability
    do {
        $round++
        $portStillHeld = $false

        # Phase 1: Collect all matching processes and their descendants, deduplicated
        $all = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue
        $targetIds = New-Object System.Collections.ArrayList
        $seenIds = @()

        foreach ($p in $procs) {
            # Add this process to collection if not already present
            if ($p.ProcessId -notin $seenIds) {
                [void]$targetIds.Add($p)
                $seenIds += $p.ProcessId
            }

            # Recursively find descendants
            $iterationLimit = 50
            $iterationCount = 0
            do {
                $newFound = $false
                $iterationCount++
                if ($iterationCount -gt $iterationLimit) {
                    break
                }
                foreach ($candidate in $all) {
                    if ($candidate.ParentProcessId -in $seenIds -and $candidate.ProcessId -notin $seenIds) {
                        [void]$targetIds.Add($candidate)
                        $seenIds += $candidate.ProcessId
                        $newFound = $true
                    }
                }
            } while ($newFound)
        }

        # Phase 2: Kill all targets (descendants first by PID descending)
        foreach ($target in ($targetIds | Sort-Object ProcessId -Descending)) {
            # Skip if already dead (might have been killed as someone else's descendant)
            $existing = Get-Process -Id $target.ProcessId -ErrorAction SilentlyContinue
            if ($null -eq $existing) {
                continue
            }

            try {
                Stop-Process -Id $target.ProcessId -Force -ErrorAction Stop
                Write-Output "[stop] $DisplayName killed pid $($target.ProcessId)"
                Write-Log "[stop] $DisplayName killed pid $($target.ProcessId)"
            }
            catch {
                Write-Output "[warn] $DisplayName failed to kill pid $($target.ProcessId): $($_.Exception.Message)"
                Write-Log "[warn] $DisplayName failed to kill pid $($target.ProcessId): $($_.Exception.Message)"
            }
        }

        # Check if we need another round (port still bound after kill)
        if ($Port -gt 0 -and $round -lt $maxRounds) {
            # Wait briefly for port release before checking
            Start-Sleep -Seconds 1
            $portStillHeld = Test-PortListening -Port $Port
            if ($portStillHeld) {
                # Re-scan for any newly forked children that might be holding the port
                $procs = Get-MatchingProcesses -ProcessName $ProcessName -CommandLinePatterns $CommandLinePatterns
                if ($null -ne $procs -and $procs.Count -gt 0) {
                    continue
                }
            }
        }
        elseif ($Port -gt 0 -and $round -ge $maxRounds) {
            $portStillHeld = Test-PortListening -Port $Port
        }
    } while ($portStillHeld -and $round -lt $maxRounds)

    # Final verification
    if ($Port -gt 0) {
        $released = Wait-PortReleased -Port $Port -TimeoutSeconds $PortReleaseTimeout
        if (-not $released) {
            Write-Output "[warn] :$Port still in use after stop -- a process not started by this script may be holding it"
            Write-Log "[warn] :$Port still in use after stop -- a process not started by this script may be holding it"
        }
    }
}

# ------------------------------------------------------------
# Stop all services
# ------------------------------------------------------------
function Stop-AllServices {
    Write-Output 'Stopping all services...'
    Write-Log 'Stopping all services...'

    # Note on matching strategy:
    # We use explicit full / partial directory paths to match only processes
    # started by this script.  A process started manually without
    # these exact command-line tokens will not be touched - this is
    # a deliberate choice to avoid killing user processes that might
    # happen to contain a similar substring.  A warning is printed if
    # a port remains occupied after the stop.

    # Stop in reverse order: tunnel first, then llm, tts, dad, son
    Stop-ServiceByName -Name 'tunnel' -DisplayName 'tunnel' -ProcessName 'cloudflared.exe' -CommandLinePatterns @("tunnel run $TunnelName") -Port 0
    Stop-ServiceByName -Name 'llm-proxy' -DisplayName 'llm-proxy' -ProcessName 'python.exe' -CommandLinePatterns @($LlmProxyScript) -Port $LlmPort
    Stop-ServiceByName -Name 'tts' -DisplayName 'tts' -ProcessName 'python.exe' -CommandLinePatterns @($TtsScript) -Port $TtsPort
    Stop-ServiceByName -Name 'dad-site' -DisplayName 'dad-site' -ProcessName 'python.exe' -CommandLinePatterns @($StaticServer, '--port 8021', $DadSiteDir) -Port $DadPort
    Stop-ServiceByName -Name 'son-site' -DisplayName 'son-site' -ProcessName 'python.exe' -CommandLinePatterns @($StaticServer, '--port 8020', $SonSiteDir) -Port $SonPort

    Write-Output 'Stop complete.'
    Write-Log 'Stop complete.'
}

# ------------------------------------------------------------
# Status check (no changes)
# ------------------------------------------------------------
function Show-Status {
    Write-Output 'Service status:'
    Write-Log 'Service status:'

    $services = @(
        @{ Name = 'son-site';   Port = $SonPort; Type = 'static' },
        @{ Name = 'dad-site';   Port = $DadPort; Type = 'static' },
        @{ Name = 'tts';        Port = $TtsPort; Type = 'health' },
        @{ Name = 'llm-proxy';  Port = $LlmPort; Type = 'health' }
    )

    foreach ($svc in $services) {
        $name = $svc.Name
        $port = $svc.Port
        $color = switch ($name) {
            'son-site'  { "$name" }
            'dad-site'  { "$name" }
            'tts'       { "$name" }
            'llm-proxy' { "$name" }
        }
        if (Test-PortListening -Port $port) {
            $healthy = Test-ServiceHealthy -Name $name -Port $port
            if ($healthy) {
                Write-Output ("[ ok ] {0,-10} :{1,-5} running (healthy)" -f $name, $port)
                Write-Log ("[ ok ] {0,-10} :{1,-5} running (healthy)" -f $name, $port)
            }
            else {
                Write-Output ("[warn] {0,-10} :{1,-5} port open but unhealthy" -f $name, $port)
                Write-Log ("[warn] {0,-10} :{1,-5} port open but unhealthy" -f $name, $port)
            }
        }
        else {
            Write-Output ("[down] {0,-10} :{1,-5} not running" -f $name, $port)
            Write-Log ("[down] {0,-10} :{1,-5} not running" -f $name, $port)
        }
    }

    # tunnel - uses process check
    if (Test-TunnelRunning) {
        Write-Output "[ ok ] tunnel             running"
        Write-Log '[ ok ] tunnel             running'
    }
    else {
        Write-Output "[down] tunnel             not running"
        Write-Log '[down] tunnel             not running'
    }
}

# ------------------------------------------------------------
# Precondition checks (start mode only)
# ------------------------------------------------------------
function Test-Preconditions {
    $errors = @()

    if (-not (Test-Path $VenvPython)) {
        $errors += "Venv Python not found: $VenvPython"
    }
    if (-not (Test-Path $SysPython)) {
        $errors += "System Python not found: $SysPython"
    }
    if (-not $SkipTunnel -and -not (Test-Path $Cloudflared)) {
        $errors += "cloudflared not found: $Cloudflared"
    }
    if (-not $SkipTunnel -and -not (Test-Path $CloudflaredConfigFile)) {
        $errors += "cloudflared config not found: $CloudflaredConfigFile"
    }
    if (-not (Test-Path $TokensFile)) {
        $errors += "Tokens file not found: $TokensFile"
    }
    if (-not (Test-Path $SonSiteDir)) {
        $errors += "Son site directory not found: $SonSiteDir"
    }
    if (-not (Test-Path $DadSiteDir)) {
        $errors += "Dad site directory not found: $DadSiteDir"
    }
    if (-not (Test-Path $StaticServer)) {
        $errors += "Static server script not found: $StaticServer"
    }
    if (-not (Test-Path $TtsScript)) {
        $errors += "TTS script not found: $TtsScript"
    }
    if (-not (Test-Path $LlmProxyScript)) {
        $errors += "LLM proxy script not found: $LlmProxyScript"
    }

    if ($errors.Count -gt 0) {
        foreach ($e in $errors) {
            Write-Output "[ERROR] $e"
            Write-Log "[ERROR] $e"
        }
        exit 2
    }
}

# ------------------------------------------------------------
# Mutex acquisition helper
# ------------------------------------------------------------
function Get-ScriptMutex {
    param([int]$TimeoutMs)
    $mutex = $null
    $acquired = $false
    try {
        $mutex = New-Object System.Threading.Mutex($false, $GlobalMutexName)
        # WaitOne can throw AbandonedMutexException if previous owner crashed.
        # Treat that as if we acquired the lock - the previous instance is gone.
        try {
            $acquired = $mutex.WaitOne($TimeoutMs, $false)
        }
        catch [System.Threading.AbandonedMutexException] {
            $acquired = $true
        }
        catch {
            $acquired = $false
        }
        if (-not $acquired) {
            Write-Output '[FAIL] another instance is running (timed out waiting for lock)'
            Write-Log '[FAIL] another instance is running (timed out waiting for lock)'
            exit 3
        }
        return $mutex
    }
    catch {
        # Fail closed - do not continue without a lock
        $errMsg = $_.Exception.Message
        Write-Output "[FAIL] could not acquire global mutex: $errMsg"
        Write-Log "[FAIL] could not acquire global mutex: $errMsg"
        exit 3
    }
}

# ------------------------------------------------------------
# Main
# ------------------------------------------------------------
$mutex = $null
try {
    # --- Ensure log directory exists (best-effort) ---
    try {
        if (-not (Test-Path $LogDir)) {
            New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
        }
    }
    catch {
        # Log dir failure is non-fatal
    }

    # Acquire the single-instance mutex
    if ($Stop -or $Status) {
        $mutex = Get-ScriptMutex -TimeoutMs $MutexTimeoutOther
    }
    else {
        $mutex = Get-ScriptMutex -TimeoutMs $MutexTimeoutStart
    }

    Write-Log "=== start_services.ps1 invoked (Status=$Status Stop=$Stop SkipTunnel=$SkipTunnel Quiet=$Quiet) ==="

    if ($Status) {
        Show-Status
        exit 0
    }

    if ($Stop) {
        Stop-AllServices
        exit 0
    }

    # --- Start mode ---
    Test-Preconditions

    Write-Log 'Starting services...'

    # Service 1: son-site (port 8020)
    $sonPatterns = @($StaticServer, '--port 8020', $SonSiteDir)
    Start-PortService -Name 'son-site' -DisplayName 'son-site' -Port $SonPort `
        -ExePath $SysPython `
        -ArgumentList @($StaticServer, '--port', '8020', '--directory', $SonSiteDir) `
        -TimeoutSeconds $DefaultTimeout `
        -MatchPatterns $sonPatterns `
        -ProcessName 'python.exe'

    # Service 2: dad-site (port 8021)
    $dadPatterns = @($StaticServer, '--port 8021', $DadSiteDir)
    Start-PortService -Name 'dad-site' -DisplayName 'dad-site' -Port $DadPort `
        -ExePath $SysPython `
        -ArgumentList @($StaticServer, '--port', '8021', '--bind', '127.0.0.1', '--directory', $DadSiteDir) `
        -TimeoutSeconds $DefaultTimeout `
        -MatchPatterns $dadPatterns `
        -ProcessName 'python.exe'

    # Service 3: tts (port 8022) - must use venv python
    $ttsPatterns = @($TtsScript)
    $ttsArgs = @('-X', 'utf8', $TtsScript, '--tokens-file', $TokensFile, '--sessions-out-dir', (Join-Path $SonSiteDir 'sessions_data'), '--sessions-per-viewer-subdir')
    Start-PortService -Name 'tts' -DisplayName 'tts' -Port $TtsPort `
        -ExePath $VenvPython `
        -ArgumentList $ttsArgs `
        -TimeoutSeconds $TtsTimeout `
        -MatchPatterns $ttsPatterns `
        -ProcessName 'python.exe'

    # Service 4: llm-proxy (port 8023)
    $llmPatterns = @($LlmProxyScript)
    $llmArgs = @($LlmProxyScript, '--port', '8023', '--upstream', 'https://api.deepseek.com/chat/completions', '--model', 'deepseek-v4-flash', '--key-env', 'DEEPSEEK_API_KEY', '--tokens-file', $TokensFile)
    Start-PortService -Name 'llm-proxy' -DisplayName 'llm-proxy' -Port $LlmPort `
        -ExePath $SysPython `
        -ArgumentList $llmArgs `
        -TimeoutSeconds $DefaultTimeout `
        -MatchPatterns $llmPatterns `
        -ProcessName 'python.exe'

    # Service 5: tunnel (no port) - starts last
    Start-TunnelService

    # Summary
    $summary = "Summary: $($script:OkCount) ok, $($script:SkipCount) skipped, $($script:FailCount) failed"
    Write-Status $summary

    if ($script:AnyFailure) {
        exit 1
    }
    else {
        exit 0
    }
}
finally {
    if ($mutex) {
        try {
            $mutex.ReleaseMutex()
        }
        catch { }
        try {
            $mutex.Dispose()
        }
        catch { }
    }
}
