$ErrorActionPreference = 'Stop'
$Root = $PSScriptRoot
$LogPath = Join-Path $Root 'OPL_STARTUP_LOG.txt'
$ServerPath = Join-Path $Root 'local_server.ps1'
$IndexPath = Join-Path $Root 'reference\ecg-id\index.html'

function Pause-On-Failure([string]$Message) {
    Write-Host ''
    Write-Host 'OPL STARTUP FAILED' -ForegroundColor Red
    Write-Host $Message -ForegroundColor Red
    Write-Host ''
    Write-Host ('Error log: ' + $LogPath) -ForegroundColor Yellow
    Write-Host ''
    Read-Host 'Press Enter to close'
}

try {
    @(
        'OpenPhysiologyLab ECG Reference Lab startup log'
        ('Started: ' + [DateTime]::Now.ToString('s'))
        ('Folder: ' + $Root)
        ''
    ) | Set-Content -Path $LogPath -Encoding UTF8

    if (-not (Test-Path -LiteralPath $ServerPath -PathType Leaf)) {
        throw 'local_server.ps1 is missing. Extract the entire ZIP before starting OPL.'
    }

    if (-not (Test-Path -LiteralPath $IndexPath -PathType Leaf)) {
        throw 'The ECG Reference Lab files are incomplete. Extract the entire ZIP before starting OPL.'
    }

    Write-Host ''
    Write-Host 'OpenPhysiologyLab ECG Reference Lab' -ForegroundColor Cyan
    Write-Host '-----------------------------------'
    Write-Host ''
    Write-Host 'Starting OPL...'
    Write-Host 'Keep this window open while using the app.'
    Write-Host ('Startup log: ' + $LogPath) -ForegroundColor DarkGray
    Write-Host ''

    & $ServerPath 2>&1 | Tee-Object -FilePath $LogPath -Append
}
catch {
    $details = $_ | Out-String
    $details | Add-Content -Path $LogPath -Encoding UTF8
    Pause-On-Failure $_.Exception.Message
    exit 1
}
