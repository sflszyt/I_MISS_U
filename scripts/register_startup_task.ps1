<#
====================================================================
 register_startup_task.ps1
====================================================================
PURPOSE:
  Register/manage a logon-triggered Scheduled Task that runs
  start_services.ps1 after logon, so the digital-memorial site comes
  back online automatically after an unattended Windows Update reboot.

USAGE (Management - run by a human):
  powershell.exe -File scripts\register_startup_task.ps1 -Register
  powershell.exe -File scripts\register_startup_task.ps1 -Unregister
  powershell.exe -File scripts\register_startup_task.ps1 -Status

USAGE (Runner - run by the Scheduled Task itself):
  powershell.exe -NoProfile -NonInteractive -WindowStyle Hidden
      -ExecutionPolicy Bypass -File scripts\register_startup_task.ps1 -Run

OPTIONAL SWITCHES:
  -SkipTunnel   Forwarded to start_services.ps1 (skip cloudflared tunnel)
  -DelaySeconds Seconds after logon before task fires (default 60,
                range 0..3600, Register mode only)

EXIT CODES (management roles):
  0 = success (always 0 for -Status)
  1 = operation failed (e.g. registration denied)
  2 = bad arguments or missing start_services.ps1

EXIT CODES (-Run role, mirrors start_services.ps1):
  0 = all required services up
  1 = at least one service failed / timed out / unverifiable
  2 = precondition check failed (bad path in start_services.ps1)

DEPENDENCY:
  scripts\start_services.ps1  (must exist beside this file)
====================================================================
#>

param(
    [switch]$Register,
    [switch]$Unregister,
    [switch]$Status,
    [switch]$Run,
    [switch]$SkipTunnel,
    [int]$DelaySeconds = 60,
    [string]$TaskName = 'ImissuStartServices'
)

$ErrorActionPreference = 'Stop'

# ------------------------------------------------------------------
# Path resolution
# ------------------------------------------------------------------
$ScriptPath = $PSCommandPath
$RepoRoot = Split-Path $PSScriptRoot -Parent
$StartServicesPath = Join-Path $PSScriptRoot 'start_services.ps1'
$LogDir = Join-Path $RepoRoot 'logs'
$TaskLog = Join-Path $LogDir 'startup_task.log'
$PowerShellExe = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'

# ------------------------------------------------------------------
# Logging helper (failures never crash the run)
# ------------------------------------------------------------------
function Write-TaskLog {
    param([string]$Message)
    try {
        if (-not (Test-Path -LiteralPath $LogDir -PathType Container)) {
            New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
        }
        $stamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
        Add-Content -LiteralPath $TaskLog -Value ("[" + $stamp + "] " + $Message) -Encoding ASCII
    } catch {
        # logging must never crash the run
    }
}

# ------------------------------------------------------------------
# Count how many of the four switch parameters were given
# ------------------------------------------------------------------
$modeCount = 0
if ($Register)   { $modeCount++ }
if ($Unregister) { $modeCount++ }
if ($Status)     { $modeCount++ }
if ($Run)        { $modeCount++ }

if ($modeCount -gt 1) {
    Write-Host "[ERROR] Only one of -Register, -Unregister, -Status, -Run may be specified."
    exit 2
}

# No parameter given => behave as -Register
if ($modeCount -eq 0) {
    $Register = $true
}

# ------------------------------------------------------------------
# DelaySeconds validation - ONLY in Register mode
# ------------------------------------------------------------------
if ($Register) {
    if ($DelaySeconds -lt 0 -or $DelaySeconds -gt 3600) {
        Write-Host "[ERROR] DelaySeconds must be between 0 and 3600."
        exit 2
    }
}

# ------------------------------------------------------------------
# start_services.ps1 presence check for -Register and -Run
# ------------------------------------------------------------------
if (($Register -or $Run) -and (-not (Test-Path -LiteralPath $StartServicesPath -PathType Leaf))) {
    Write-Host "[ERROR] Required file not found: $StartServicesPath"
    exit 2
}

# ------------------------------------------------------------------
# -Run: what the Scheduled Task executes
# ------------------------------------------------------------------
if ($Run) {
    $maxAttempts = 3
    $retryDelaySeconds = 120
    $childTimeoutMs = 900000   # 15 minutes
    $hadTimeout = $false

    function Test-ServicesHealthy {
        param([bool]$SkipTunnelFlag)

        # Build the argument array ONCE, cleanly
        $statusArgs = @('-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File', $StartServicesPath, '-Status')

        # Required services: always these five
        $required = @('son-site', 'dad-site', 'son-public', 'tts', 'llm-proxy')
        if (-not $SkipTunnelFlag) {
            $required += 'tunnel'
        }

        $tempOut = Join-Path $env:TEMP ('svc_status_' + [guid]::NewGuid().ToString() + '.txt')
        $proc = $null
        try {
            $proc = Start-Process -FilePath $PowerShellExe -ArgumentList $statusArgs -PassThru -WindowStyle Hidden -WorkingDirectory $RepoRoot -RedirectStandardOutput $tempOut
        } catch {
            $proc = $null
        }

        # Open the process handle while the child is still alive. Without a cached
        # handle, a Start-Process -PassThru object reports ExitCode as $null after
        # exit (verified 2026-09-11), which made this gate always return false.
        if ($null -ne $proc) { try { $null = $proc.Handle } catch { } }

        if ($null -eq $proc) {
            return $false
        }

        $exitedInTime = $proc.WaitForExit(120000)
        if (-not $exitedInTime) {
            try { $proc.Kill() } catch { }
            return $false
        }

        $proc.Refresh()
        $statusExit = $proc.ExitCode
        if ($statusExit -ne 0) {
            return $false
        }

        # Read the output file
        $content = $null
        try {
            if (Test-Path -LiteralPath $tempOut -PathType Leaf) {
                $content = Get-Content -LiteralPath $tempOut -Raw
            }
        } catch {
            $content = $null
        }

        $healthy = $true
        if ($null -eq $content) {
            $healthy = $false
        } else {
            foreach ($svc in $required) {
                $pattern = '\[ ok \].*' + [regex]::Escape($svc)
                if ($content -notmatch $pattern) {
                    $healthy = $false
                    break
                }
            }
        }

        # cleanup in finally
        try {
            if (Test-Path -LiteralPath $tempOut -PathType Leaf) {
                Remove-Item -LiteralPath $tempOut -Force
            }
        } catch {
            # failure to delete must not change the verdict
        }

        return $healthy
    }

    for ($attempt = 1; $attempt -le $maxAttempts; $attempt++) {
        $proc = $null
        $childArgs = @('-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File', $StartServicesPath)
        if ($SkipTunnel) { $childArgs += '-SkipTunnel' }

        # Launch phase - test ONLY $proc
        try {
            $proc = Start-Process -FilePath $PowerShellExe -ArgumentList $childArgs -PassThru -WindowStyle Hidden -WorkingDirectory $RepoRoot
        } catch {
            $proc = $null
        }

        # Cache the handle so ExitCode is readable after exit (see Test-ServicesHealthy).
        if ($null -ne $proc) { try { $null = $proc.Handle } catch { } }

        if ($null -eq $proc) {
            Write-TaskLog ("run attempt " + $attempt + "/" + $maxAttempts + " exit=launch-failed")
            if ($attempt -lt $maxAttempts) {
                Start-Sleep -Seconds $retryDelaySeconds
                continue
            } else {
                Write-Host "[FAIL] launch of start_services.ps1 failed after $maxAttempts attempts"
                exit 1
            }
        }

        # Wait for the child (NOT its descendants)
        $exitedInTime = $proc.WaitForExit($childTimeoutMs)
        $code = $null
        $killedOnTimeout = $false

        if (-not $exitedInTime) {
            # Hung child: kill it and count this attempt as a failure
            $hadTimeout = $true
            try { $proc.Kill() } catch { }
            $killConfirmed = $false
            try { $killConfirmed = $proc.WaitForExit(10000) } catch { $killConfirmed = $false }
            if (-not $killConfirmed) {
                try { $proc.Refresh(); $killConfirmed = $proc.HasExited } catch { $killConfirmed = $false }
            }
            if (-not $killConfirmed) {
                Write-TaskLog "exit=timeout child could not be killed - aborting"
                Write-Host "[FAIL] child process could not be killed after timeout - aborting (zombie mutex risk)"
                exit 1
            }
            Write-TaskLog ("run attempt " + $attempt + "/" + $maxAttempts + " exit=timeout child killed after 900s")
            $code = 1
            $killedOnTimeout = $true
        } else {
            $proc.Refresh()
            $code = $proc.ExitCode
            if ($null -eq $code) { $code = 1 }
        }

        # Now dispatch on exit code
        if ($code -eq 0) {
            Write-TaskLog ("run attempt " + $attempt + "/" + $maxAttempts + " exit=0 all services up")
            Write-Host "[ ok ] all services up"
            exit 0
        }
        elseif ($code -eq 2) {
            # Precondition failure - retrying cannot help
            Write-TaskLog ("run attempt " + $attempt + "/" + $maxAttempts + " exit=2 precondition failed - aborting")
            Write-Host "[FAIL] precondition check failed in start_services.ps1 - aborting"
            exit 2
        }
        elseif ($code -eq 3) {
            # Mutex held - verify actual service state before deciding
            Write-TaskLog ("run attempt " + $attempt + "/" + $maxAttempts + " exit=3 mutex held (hadTimeout=" + $hadTimeout + ") - verifying service state")
            $healthy = Test-ServicesHealthy -SkipTunnelFlag $SkipTunnel
            if ($healthy) {
                Write-TaskLog ("run attempt " + $attempt + "/" + $maxAttempts + " exit=3 mutex held, but -Status verified all required services healthy")
                Write-Host "[ ok ] services verified healthy via status probe"
                exit 0
            } else {
                Write-TaskLog ("run attempt " + $attempt + "/" + $maxAttempts + " exit=3 mutex held and services NOT verified healthy")
                Write-Host "[FAIL] mutex held but services not verified healthy"
                exit 1
            }
        }
        elseif ($code -eq 1 -or $killedOnTimeout) {
            if ($attempt -lt $maxAttempts) {
                Write-TaskLog ("run attempt " + $attempt + "/" + $maxAttempts + " exit=1 - will retry")
                Start-Sleep -Seconds $retryDelaySeconds
            } else {
                Write-TaskLog ("run attempt " + $attempt + "/" + $maxAttempts + " exit=1 - giving up after " + $maxAttempts + " attempts")
                Write-Host "[FAIL] at least one service failed to start after $maxAttempts attempts"
                exit 1
            }
        }
        else {
            if ($attempt -lt $maxAttempts) {
                Write-TaskLog ("run attempt " + $attempt + "/" + $maxAttempts + " exit=" + $code + " unexpected - will retry")
                Start-Sleep -Seconds $retryDelaySeconds
            } else {
                Write-TaskLog ("run attempt " + $attempt + "/" + $maxAttempts + " exit=" + $code + " unexpected - giving up")
                Write-Host "[FAIL] unexpected exit code $code from start_services.ps1"
                exit 1
            }
        }
    }

    # Should never reach here
    Write-Host "[FAIL] unexpected control flow end"
    exit 1
}

# ------------------------------------------------------------------
# -Register: create/replace the Scheduled Task
# ------------------------------------------------------------------
if ($Register) {
    $principalUser = "$env:USERDOMAIN\$env:USERNAME"

    Write-TaskLog "register: starting registration for task '$TaskName'"

    # Task action arguments
    $actionArgs = '-NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File "' + $ScriptPath + '" -Run'
    if ($SkipTunnel) {
        $actionArgs += ' -SkipTunnel'
    }

    # Build the task
    $action = New-ScheduledTaskAction -Execute $PowerShellExe -Argument $actionArgs -WorkingDirectory $RepoRoot
    $trigger = New-ScheduledTaskTrigger -AtLogOn -User $principalUser
    $trigger.Delay = 'PT' + $DelaySeconds + 'S'
    $principal = New-ScheduledTaskPrincipal -UserId $principalUser -LogonType Interactive -RunLevel Limited

    $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Hours 1) -MultipleInstances IgnoreNew -StartWhenAvailable -Hidden

    # Deliberately NOT configuring RestartOnFailure: Windows only triggers it
    # when the task fails to LAUNCH, not on a non-zero exit code. Our own -Run
    # retry loop is the real retry mechanism.

    # Check existence WITHOUT deleting anything
    $taskExists = $false
    try {
        $existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
        if ($null -ne $existing) { $taskExists = $true }
    } catch {
        $taskExists = $false
    }

    # Register with -Force (atomically replaces existing task)
    try {
        Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force | Out-Null
    } catch {
        Write-Host "[FAIL] Could not register task '$TaskName': $($_.Exception.Message)"
        Write-Host "[FAIL] If this is an access/permission error, re-run from an elevated PowerShell."
        Write-TaskLog "register: FAILED - $($_.Exception.Message)"
        exit 1
    }

    # Only now report success, based on whether it existed before
    if ($taskExists) {
        Write-Host "[ ok ] replaced existing task '$TaskName'"
    } else {
        Write-Host "[ ok ] registered task '$TaskName'"
    }

    # Read back and display resolved action
    try {
        $registered = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
        if ($null -ne $registered) {
            Write-Host "[ ok ] action Execute: $($registered.Actions[0].Execute)"
            Write-Host "[ ok ] action Arguments: $($registered.Actions[0].Arguments)"
        }
    } catch {
        Write-Host "[warn] task registered but could not be read back"
    }

    Write-TaskLog "register: registration completed successfully"
    exit 0
}

# ------------------------------------------------------------------
# -Unregister
# ------------------------------------------------------------------
if ($Unregister) {
    $taskExists = $false
    try {
        $existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
        if ($null -ne $existing) { $taskExists = $true }
    } catch {
        $taskExists = $false
    }

    if (-not $taskExists) {
        Write-Host "[ ok ] task '$TaskName' is not registered (nothing to do)"
        exit 0
    }

    try {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
        Write-Host "[ ok ] unregistered task '$TaskName'"
        Write-TaskLog "unregister: task '$TaskName' removed"
        exit 0
    } catch {
        Write-Host "[FAIL] could not unregister task '$TaskName': $($_.Exception.Message)"
        Write-TaskLog "unregister: FAILED - $($_.Exception.Message)"
        exit 1
    }
}

# ------------------------------------------------------------------
# -Status (ALWAYS exits 0)
# ------------------------------------------------------------------
if ($Status) {
    $taskExists = $false
    $task = $null
    try {
        $task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
        if ($null -ne $task) { $taskExists = $true }
    } catch {
        $taskExists = $false
    }

    if (-not $taskExists) {
        Write-Host "[down] task '$TaskName' is not registered"
        exit 0
    }

    # Column header
    Write-Host ("{0,-18} {1,-15} {2,-22} {3,-15} {4,-22}" -f 'task name','State','LastRunTime','LastTaskResult','NextRunTime')

    $info = $null
    try {
        $info = Get-ScheduledTaskInfo -TaskName $TaskName -ErrorAction SilentlyContinue
    } catch {
        $info = $null
    }

    $state = 'unknown'
    try { $state = $task.State.ToString() } catch { $state = 'unknown' }

    # LastRunTime: treat years before 2000 as "never ran"
    $lastRun = '-'
    $nextRun = '-'
    if ($null -ne $info) {
        try {
            if ($info.LastRunTime.Year -ge 2000) {
                $lastRun = $info.LastRunTime.ToString('yyyy-MM-dd HH:mm:ss')
            }
        } catch { $lastRun = '-' }

        try {
            if ($info.NextRunTime.Year -ge 2000) {
                $nextRun = $info.NextRunTime.ToString('yyyy-MM-dd HH:mm:ss')
            }
        } catch { $nextRun = '-' }
    }

    # LastTaskResult: coerce defensively to int64
    $resultCode = $null
    if ($null -ne $info) {
        try {
            $raw = $info.LastTaskResult
            if ($null -ne $raw) {
                $resultCode = [int64]$raw
            }
        } catch {
            $resultCode = $null
        }
    }

    $resultText = '-'
    if ($null -ne $resultCode) {
        switch ($resultCode) {
            0      { $resultText = 'all services up' }
            1      { $resultText = 'at least one service FAILED' }
            2      { $resultText = 'precondition check failed (bad path in start_services.ps1)' }
            3      { $resultText = 'another instance held the lock' }
            267009 { $resultText = 'currently running' }
            267011 { $resultText = 'has not run yet' }
            default { $resultText = 'raw code: ' + $resultCode }
        }
    }

    # Aligned output row
    Write-Host ("{0,-18} {1,-15} {2,-22} {3,-15} {4,-22}" -f $TaskName, $state, $lastRun, $resultCode, $nextRun)
    Write-Host ("  (interpretation: " + $resultText + ")")

    # Action detail
    try {
        $acts = $task.Actions
        if ($acts.Count -gt 0) {
            $idx = 0
            while ($idx -lt $acts.Count) {
                $a = $acts[$idx]
                Write-Host ("  action Execute: " + $a.Execute)
                Write-Host ("  action Arguments: " + $a.Arguments)
                $idx++
            }
        }
    } catch {
        Write-Host "[warn] could not read task actions"
    }

    exit 0
}

# Should never get here
Write-Host "[warn] no valid mode selected"
exit 2