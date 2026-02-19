param(
  [string]$WorkerId = $env:RAYVAULT_WORKER_ID,
  [string]$Host = $env:RAYVAULT_WORKER_HOST,
  [int]$Port = $(if ($env:RAYVAULT_WORKER_PORT) { [int]$env:RAYVAULT_WORKER_PORT } else { 8787 }),
  [string]$WorkspaceRoot = $(if ($env:RAYVAULT_WORKER_ROOT) { $env:RAYVAULT_WORKER_ROOT } else { "state/cluster/worker_data" }),
  [string]$RepoRoot = ""
)

$ErrorActionPreference = "Stop"

if (-not $RepoRoot) {
  $RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "../..")
}

if (-not $WorkerId) {
  $WorkerId = $env:COMPUTERNAME
}

if (-not $Host) {
  try {
    $tailscaleIp = tailscale ip -4 2>$null | Select-Object -First 1
    if ($tailscaleIp) {
      $Host = $tailscaleIp.Trim()
    }
  } catch {
    # no-op
  }
}

if (-not $Host) {
  $Host = "127.0.0.1"
}

if (-not $env:RAYVAULT_CLUSTER_SECRET) {
  Write-Host "ERROR: define RAYVAULT_CLUSTER_SECRET before starting worker." -ForegroundColor Red
  exit 1
}

$pythonCmd = $null
$pythonPrefixArgs = @()
if (Get-Command py -ErrorAction SilentlyContinue) {
  # Prefer explicit Python 3.11+ launcher on Windows.
  $pythonCmd = "py"
  $pythonPrefixArgs = @("-3.11")
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
  $pythonCmd = "python"
} else {
  Write-Host "ERROR: Python not found. Install Python 3.11+ and ensure py/python is in PATH." -ForegroundColor Red
  exit 1
}

Push-Location $RepoRoot
try {
  Write-Host "Starting RayVault worker: $WorkerId on $Host`:$Port"
  & $pythonCmd @pythonPrefixArgs -m rayvault.agent.worker_server `
    --host $Host `
    --port $Port `
    --worker-id $WorkerId `
    --workspace-root $WorkspaceRoot `
    --cluster-secret $env:RAYVAULT_CLUSTER_SECRET
} finally {
  Pop-Location
}
