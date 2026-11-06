Set-StrictMode -Version Latest

$script:LokiEnvironmentUrls = @{
    staging    = "https://loki-dev.staging-colossusbets.com"
    production = "https://loki-dev.colossusbets.com"
}

function Unlock-LokiSecretStore {
    <#
    .SYNOPSIS
    Unlock SecretStore only when needed.
    #>
    try {
        Get-SecretInfo -Name "loki-env-staging" -ErrorAction Stop | Out-Null
        return
    } catch {
        $password = Read-Host "SecretStore password" -AsSecureString
        Unlock-SecretStore -Password $password
    }
}

function Set-LokiEnv {
    <#
    .SYNOPSIS
    Load LOKI_* environment variables for an environment.
    #>
    param(
        [Parameter(Mandatory = $true)]
        [ValidateSet("staging", "production")]
        [string]$Environment
    )

    $secretName = "loki-env-$Environment"
    $json = Get-Secret -Name $secretName -AsPlainText
    if ([string]::IsNullOrWhiteSpace($json)) {
        throw "Secret '$secretName' is empty or missing."
    }

    $cfg = $json | ConvertFrom-Json
    if (-not $cfg.loki_username -or -not $cfg.loki_password) {
        throw "Secret '$secretName' must include loki_username and loki_password."
    }

    $env:LOKI_ADDR = if ($cfg.loki_addr) { [string]$cfg.loki_addr } else { $script:LokiEnvironmentUrls[$Environment] }
    $env:LOKI_USERNAME = [string]$cfg.loki_username
    $env:LOKI_PASSWORD = [string]$cfg.loki_password

    Write-Host "Loaded Loki env for $Environment"
}

function Test-LokiAuth {
    <#
    .SYNOPSIS
    Quick auth sanity check against Loki labels endpoint.
    #>
    param(
        [string]$Since = "5m"
    )

    & logcli --addr="$env:LOKI_ADDR" --username="$env:LOKI_USERNAME" --password="$env:LOKI_PASSWORD" labels --since="$Since"
}

function Get-LokiLogs {
    <#
    .SYNOPSIS
    Query Loki logs with preloaded LOKI_* environment variables.
    #>
    param(
        [Parameter(Mandatory = $true)]
        [string]$Query,
        [string]$Since = "1h",
        [int]$Limit = 80
    )

    $isWindowsPlatform = $env:OS -eq "Windows_NT"
    if ($isWindowsPlatform) {
        $escapedQuery = $Query.Replace('"', '\"')
        $cmd = "logcli --addr=%LOKI_ADDR% --username=%LOKI_USERNAME% --password=%LOKI_PASSWORD% query ""$escapedQuery"" --since=$Since --limit=$Limit --quiet"
        cmd /c $cmd
        return
    }

    & logcli --addr="$env:LOKI_ADDR" --username="$env:LOKI_USERNAME" --password="$env:LOKI_PASSWORD" query "$Query" --since="$Since" --limit="$Limit" --quiet
}

function Clear-LokiEnv {
    Remove-Item Env:LOKI_ADDR -ErrorAction SilentlyContinue
    Remove-Item Env:LOKI_USERNAME -ErrorAction SilentlyContinue
    Remove-Item Env:LOKI_PASSWORD -ErrorAction SilentlyContinue
    Write-Host "Cleared Loki environment variables for this session"
}

