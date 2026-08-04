<#
.SYNOPSIS
  Delegate a coding task to DeepSeek V4 Flash (per project iron rules).

.DESCRIPTION
  Reads DEEPSEEK_API_KEY from the environment, sends a chat completion
  request to the DeepSeek API (OpenAI-compatible), and prints the final
  answer (the code) to stdout. Reasoning, usage, and warnings go to stderr
  so stdout stays clean for piping / writing to a file.

  DeepSeek V4 Flash is a REASONING model: it emits reasoning_content that
  consumes tokens. MaxTokens defaults high so real code is not truncated.

.EXAMPLE
  powershell -NoProfile -ExecutionPolicy Bypass -File scripts\deepseek.ps1 -PromptFile spec.txt -OutFile src\thing.py

.EXAMPLE
  "write a python function that reverses a string" | powershell -File scripts\deepseek.ps1
#>
[CmdletBinding()]
param(
    [string]$Prompt,
    [string]$PromptFile,
    [string]$System,
    [string]$SystemFile,
    [string]$Model = "deepseek-v4-flash",
    [int]$MaxTokens = 8192,
    [double]$Temperature,
    [string]$OutFile,
    [switch]$ShowReasoning,
    [switch]$Raw
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

# --- API key -------------------------------------------------------------
$key = $env:DEEPSEEK_API_KEY
if (-not $key) { $key = [Environment]::GetEnvironmentVariable("DEEPSEEK_API_KEY", "User") }
if (-not $key) {
    [Console]::Error.WriteLine("[error] DEEPSEEK_API_KEY is not set (env var, User scope).")
    exit 1
}

# --- Prompt --------------------------------------------------------------
if ($PromptFile) {
    if (-not (Test-Path $PromptFile)) { [Console]::Error.WriteLine("[error] PromptFile not found: $PromptFile"); exit 1 }
    $Prompt = Get-Content -Raw -Encoding UTF8 $PromptFile
}
if (-not $Prompt -and -not $PromptFile) {
    if ([Console]::IsInputRedirected) { $Prompt = [Console]::In.ReadToEnd() }
}
if (-not $Prompt) { [Console]::Error.WriteLine("[error] No prompt provided (use -Prompt, -PromptFile, or pipe stdin)."); exit 1 }

# --- System prompt -------------------------------------------------------
if ($SystemFile) { $System = Get-Content -Raw -Encoding UTF8 $SystemFile }
if (-not $System) {
    $System = "You are an expert software engineer acting as the code-writing engine inside a larger, Claude-orchestrated workflow. Implement exactly what the specification asks. Output the requested code with correct file paths and nothing else — no preamble, no explanation, no summary — unless the spec explicitly asks for it. Prefer complete, runnable code over snippets."
}

# --- Request body --------------------------------------------------------
$bodyObj = @{
    model      = $Model
    messages   = @(
        @{ role = "system"; content = $System },
        @{ role = "user";   content = $Prompt }
    )
    max_tokens = $MaxTokens
    stream     = $false
}
if ($PSBoundParameters.ContainsKey('Temperature')) { $bodyObj.temperature = $Temperature }

$json  = $bodyObj | ConvertTo-Json -Depth 12
$bytes = [System.Text.Encoding]::UTF8.GetBytes($json)

# --- Call (with retry: long generations can hit dropped connections) -----
[System.Net.ServicePointManager]::SecurityProtocol = [System.Net.SecurityProtocolType]::Tls12
[System.Net.ServicePointManager]::DefaultConnectionLimit = 16
$maxAttempts = 3
$resp = $null
for ($attempt = 1; $attempt -le $maxAttempts; $attempt++) {
    try {
        $resp = Invoke-RestMethod -Uri "https://api.deepseek.com/chat/completions" `
            -Method Post `
            -Headers @{ Authorization = "Bearer $key" } `
            -ContentType "application/json; charset=utf-8" `
            -TimeoutSec 1800 `
            -Body $bytes
        break
    } catch {
        [Console]::Error.WriteLine("[warn] attempt $attempt/$maxAttempts failed: " + $_.Exception.Message)
        if ($_.ErrorDetails -and $_.ErrorDetails.Message) { [Console]::Error.WriteLine($_.ErrorDetails.Message) }
        if ($attempt -eq $maxAttempts) {
            [Console]::Error.WriteLine("[error] DeepSeek API call failed after $maxAttempts attempts.")
            exit 1
        }
        Start-Sleep -Seconds (5 * $attempt)
    }
}

if ($Raw) {
    ($resp | ConvertTo-Json -Depth 20)
    exit 0
}

$choice    = $resp.choices[0]
$content   = $choice.message.content
$reasoning = $choice.message.reasoning_content
$finish    = $choice.finish_reason

if ($ShowReasoning -and $reasoning) {
    [Console]::Error.WriteLine("----- reasoning -----")
    [Console]::Error.WriteLine($reasoning)
    [Console]::Error.WriteLine("---------------------")
}
if ($resp.usage) {
    [Console]::Error.WriteLine("[usage] prompt=$($resp.usage.prompt_tokens) completion=$($resp.usage.completion_tokens) total=$($resp.usage.total_tokens)")
}
if ($finish -eq "length") {
    [Console]::Error.WriteLine("[warn] finish_reason=length -> output truncated. Re-run with a higher -MaxTokens.")
}

# --- Output --------------------------------------------------------------
if ($OutFile) {
    $full = $OutFile
    if (-not [System.IO.Path]::IsPathRooted($full)) { $full = Join-Path (Get-Location).Path $full }
    $dir = Split-Path $full -Parent
    if ($dir -and -not (Test-Path $dir)) { New-Item -ItemType Directory -Force -Path $dir | Out-Null }
    [System.IO.File]::WriteAllText($full, $content, (New-Object System.Text.UTF8Encoding($false)))
    [Console]::Error.WriteLine("[written] $full")
} else {
    [Console]::Out.Write($content)
}
