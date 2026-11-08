# Manage only this review service. No tunnel or legacy service changes.
# Exit: 0 ready/stopped/optional config absent; 1 failed/down; 2 invalid config; 3 busy.
param(
    [switch]$Status,
    [switch]$Stop,
    [string]$ConfigPath = '',
    [ValidateRange(2,120)][int]$TimeoutSeconds = 30
)
$ErrorActionPreference = 'Stop'
$RepoRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $RepoRoot 'data\runtime\mobile-review-venv\Scripts\python.exe'
$Server = Join-Path $RepoRoot 'tools\mobile_review_server.py'
if (-not $ConfigPath) {
    $ConfigPath = Join-Path $RepoRoot 'people\mama\reviews\mobile-20261022-v1\server-config.json'
}
$ConfigPath = [IO.Path]::GetFullPath($ConfigPath)

# All arguments are quoted with the Windows CRT escaping convention.
function Quote-Argument([string]$Value) {
    return '"' + [regex]::Replace([regex]::Replace($Value, '(\\*)"', '$1$1\"'), '(\\+)$', '$1$1') + '"'
}
function Get-Identity([int]$ProcessId) {
    return Get-CimInstance Win32_Process -Filter "ProcessId = $ProcessId" -ErrorAction Stop
}
function Get-OwnedProcess($Record) {
    if (-not $Record -or $Record.config -cne $ConfigPath -or $Record.arguments -cne $Arguments) { return $null }
    if ($Record.executable -ine $Python -or $Record.command.Trim() -cne ((Quote-Argument $Python) + ' ' + $Arguments)) { return $null }
    $p = Get-Identity ([int]$Record.pid)
    if ($p -and $p.CreationDate.ToUniversalTime().Ticks.ToString() -eq $Record.created -and
        $p.ExecutablePath -ieq $Record.executable -and $p.CommandLine -ceq $Record.command) {
        return $p
    }
    return $null
}
function Get-Listeners {
    return @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
}
function Test-HttpReady {
    # HttpWebRequest rewrites a default-port Host on .NET/PowerShell 7.
    # HttpClient preserves the exact configured authority on the wire.
    Add-Type -AssemblyName System.Net.Http
    $handler = [Net.Http.HttpClientHandler]::new()
    $handler.UseProxy = $false
    $handler.AllowAutoRedirect = $false
    $client = [Net.Http.HttpClient]::new($handler)
    $client.Timeout = [TimeSpan]::FromSeconds(2)
    $cancel = [Threading.CancellationTokenSource]::new()
    $request = [Net.Http.HttpRequestMessage]::new([Net.Http.HttpMethod]::Get, "http://127.0.0.1:$Port/review/api/session")
    $request.Headers.Host = ([Uri]$Config.public_origin).Authority
    $response = $null
    $stream = $null
    try {
        # One deadline covers headers and all body reads (ResponseHeadersRead
        # otherwise stops HttpClient.Timeout once headers have arrived).
        $clock = [Diagnostics.Stopwatch]::StartNew()
        $cancel.CancelAfter(2000)
        $response = $client.SendAsync($request, [Net.Http.HttpCompletionOption]::ResponseHeadersRead, $cancel.Token).GetAwaiter().GetResult()
        if ([int]$response.StatusCode -ne 401) { return $false }
        $stream = $response.Content.ReadAsStreamAsync().GetAwaiter().GetResult()
        $buffer = New-Object byte[] 4097
        $length = 0
        do {
            # .NET Framework's response stream may ignore ReadAsync cancellation.
            # Bound the wait itself as well as supplying the cancellation token.
            $remaining = 2000 - [int]$clock.ElapsedMilliseconds
            if ($remaining -le 0) { return $false }
            $pending = $stream.ReadAsync($buffer, $length, $buffer.Length - $length, $cancel.Token)
            if (-not $pending.Wait($remaining)) { $cancel.Cancel(); return $false }
            $read = $pending.GetAwaiter().GetResult()
            $length += $read
        } while ($read -gt 0 -and $length -lt $buffer.Length)
        if ($length -eq 0 -or $length -gt 4096) { return $false }
        $body = ([Text.UTF8Encoding]::new($false, $true)).GetString($buffer, 0, $length) | ConvertFrom-Json
        return ($body.error.code -ceq 'authentication_required')
    } catch { return $false }
    finally {
        if ($stream) { $stream.Dispose() }
        if ($response) { $response.Dispose() }
        $request.Dispose()
        $cancel.Dispose()
        $client.Dispose()
    }
}
function Test-Ready($Record) {
    $p = Get-OwnedProcess $Record
    if (-not $p) { return $false }
    $listeners = @(Get-Listeners)
    # Windows venv python.exe is a redirector; the base interpreter owns the socket.
    $worker = Get-CimInstance Win32_Process -Filter "ParentProcessId = $($p.ProcessId)" -ErrorAction Stop |
        Where-Object { $_.ExecutablePath -ieq $BasePython -and $_.CommandLine -and
            $_.CommandLine.Trim() -ceq ((Quote-Argument $BasePython) + ' ' + $Arguments) }
    $ownerId = $p.ProcessId
    if (@($worker).Count -gt 1) { return $false }
    if ($worker) { $ownerId = $worker.ProcessId }
    if ($listeners.Count -ne 1 -or $listeners[0].OwningProcess -ne $ownerId -or
        $listeners[0].LocalAddress -ne '127.0.0.1') { return $false }
    # A denied private API request proves the HTTP/auth pipeline is responding.
    # Do not fetch private data or require a public health endpoint.
    return (Test-HttpReady)
}
function Stop-Owned($Record) {
    $p = Get-OwnedProcess $Record
    if (-not $p) { return }
    # Open and retain a handle, then re-check identity before termination (PID reuse).
    $process = Get-Process -Id $p.ProcessId -ErrorAction Stop
    try {
        $null = $process.Handle
        if (-not (Get-OwnedProcess $Record)) { throw 'Process identity changed; refusing stop.' }
        $process.Kill()
        if (-not $process.WaitForExit(10000)) { throw 'Owned process did not exit.' }
    } finally { $process.Dispose() }
}

$mutex = $null
$locked = $false
$record = $null
$started = $false
$child = $null
$failureCode = 2
try {
    if ($Status -and $Stop) { throw 'Choose Status or Stop.' }
    if (-not (Test-Path -LiteralPath $ConfigPath -PathType Leaf)) {
        Write-Output '[skip] mobile-review config absent'
        exit 0
    }
    $Config = Get-Content -LiteralPath $ConfigPath -Raw | ConvertFrom-Json
    $Port = [int]$Config.port
    if ($Config.host -cne '127.0.0.1' -or $Port -lt 1024 -or $Port -gt 65535 -or
        -not ([Uri]$Config.public_origin).IsAbsoluteUri) { throw 'Invalid loopback service config.' }
    if (-not (Test-Path -LiteralPath $Python -PathType Leaf) -or
        -not (Test-Path -LiteralPath $Server -PathType Leaf)) { throw 'Review runtime or server missing.' }
    $venvConfig = Get-Content -LiteralPath (Join-Path (Split-Path (Split-Path $Python)) 'pyvenv.cfg')
    $baseHome = @($venvConfig | Where-Object { $_ -match '^home = ' })
    if ($baseHome.Count -ne 1) { throw 'Invalid review virtual environment.' }
    $BasePython = Join-Path $baseHome[0].Substring(7) 'python.exe'
    $Arguments = ((@('-X', 'utf8', $Server, '--config', $ConfigPath) | ForEach-Object { Quote-Argument $_ }) -join ' ')
    $sha = [Security.Cryptography.SHA256]::Create()
    try { $key = ([BitConverter]::ToString($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($ConfigPath.ToLowerInvariant())))).Replace('-', '').Substring(0,24) }
    finally { $sha.Dispose() }
    $ControlDir = Join-Path $RepoRoot 'data\runtime\mobile-review-processes'
    $RecordPath = Join-Path $ControlDir ($key + '.json')
    $mutex = New-Object Threading.Mutex($false, "Global\ImissuMobileReview_$key")
    try { $locked = $mutex.WaitOne(30000) }
    catch [Threading.AbandonedMutexException] { $locked = $true }
    if (-not $locked) { Write-Output '[FAIL] mobile-review busy'; exit 3 }
    $failureCode = 1
    if (Test-Path -LiteralPath $RecordPath) { $record = Get-Content -LiteralPath $RecordPath -Raw | ConvertFrom-Json }
    $owned = Get-OwnedProcess $record
    if ($Status) {
        if (Test-Ready $record) { Write-Output '[ ok ] mobile-review running (authenticated routes protected)'; exit 0 }
        Write-Output '[down] mobile-review not ready or not owned'; exit 1
    }
    if ($Stop) {
        if ($owned) {
            Stop-Owned $record
            Remove-Item -LiteralPath $RecordPath -Force
            Write-Output '[ ok ] mobile-review stopped'
        } elseif (@(Get-Listeners).Count) {
            Write-Output '[FAIL] mobile-review foreign listener; refusing stop'; exit 1
        } else { Write-Output '[ ok ] mobile-review already stopped' }
        exit 0
    }
    if ($owned) {
        if (Test-Ready $record) { Write-Output '[ ok ] mobile-review already running'; exit 0 }
        Write-Output '[FAIL] mobile-review owned process unhealthy; explicit Stop required'; exit 1
    }
    if (@(Get-Listeners).Count) { Write-Output '[FAIL] mobile-review foreign listener; refusing start'; exit 1 }
    New-Item -ItemType Directory -Force -Path $ControlDir | Out-Null
    $logPrefix = Join-Path $ControlDir ($key + '-' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff'))
    $child = Start-Process -FilePath $Python -ArgumentList $Arguments -WorkingDirectory $RepoRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput ($logPrefix + '.out.log') -RedirectStandardError ($logPrefix + '.err.log')
    $null = $child.Handle
    $started = $true
    $p = Get-Identity $child.Id
    if (-not $p -or $p.ExecutablePath -ine $Python) { throw 'Cannot establish launched process identity.' }
    $record = @{ pid = $p.ProcessId; created = $p.CreationDate.ToUniversalTime().Ticks.ToString(); executable = $p.ExecutablePath; command = $p.CommandLine; config = $ConfigPath; arguments = $Arguments }
    $temporary = $RecordPath + '.tmp'
    $record | ConvertTo-Json | Set-Content -LiteralPath $temporary -Encoding UTF8
    Move-Item -LiteralPath $temporary -Destination $RecordPath -Force
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        if ($child.HasExited) { throw "Review process exited with code $($child.ExitCode)." }
        if (Test-Ready $record) { $started = $false; Write-Output '[ ok ] mobile-review started'; exit 0 }
        Start-Sleep -Milliseconds 250
    } while ((Get-Date) -lt $deadline)
    throw 'Review readiness timed out.'
} catch {
    # Deliberately do not print config content or exception paths/private details.
    Write-Output '[FAIL] mobile-review operation failed; inspect local review logs/config'
    if ($started) {
        try {
            if ($record) { Stop-Owned $record }
            elseif ($child -and -not $child.HasExited) { $child.Kill(); $null = $child.WaitForExit(10000) }
        } catch { Write-Output '[FAIL] mobile-review cleanup failed; manual inspection required' }
    }
    exit $failureCode
} finally {
    if ($child) { $child.Dispose() }
    if ($locked) { $mutex.ReleaseMutex() }
    if ($mutex) { $mutex.Dispose() }
}
