param(
    [int]$StartPort = 8765,
    [switch]$NoBrowser
)

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$RootFull = [System.IO.Path]::GetFullPath($Root)

function Get-MimeType([string]$Path) {
    switch ([System.IO.Path]::GetExtension($Path).ToLowerInvariant()) {
        '.html' { 'text/html; charset=utf-8' }
        '.css' { 'text/css; charset=utf-8' }
        '.js' { 'text/javascript; charset=utf-8' }
        '.mjs' { 'text/javascript; charset=utf-8' }
        '.json' { 'application/json; charset=utf-8' }
        '.webmanifest' { 'application/manifest+json; charset=utf-8' }
        '.svg' { 'image/svg+xml' }
        '.png' { 'image/png' }
        '.ico' { 'image/x-icon' }
        '.txt' { 'text/plain; charset=utf-8' }
        '.md' { 'text/markdown; charset=utf-8' }
        default { 'application/octet-stream' }
    }
}

$Listener = $null
$Port = $StartPort
while ($Port -lt ($StartPort + 30)) {
    try {
        $Listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, $Port)
        $Listener.Start()
        break
    } catch {
        if ($Listener) { try { $Listener.Stop() } catch {} }
        $Listener = $null
        $Port++
    }
}

if (-not $Listener) {
    Write-Host 'Could not find a free local port.' -ForegroundColor Red
    Read-Host 'Press Enter to close'
    exit 1
}

$Url = "http://127.0.0.1:$Port/reference/ecg-id/index.html"
Write-Host ''
Write-Host 'OpenPhysiologyLab ECG Reference Lab' -ForegroundColor Cyan
Write-Host '-----------------------------------'
Write-Host "Serving: $RootFull"
Write-Host "Open:    $Url"
Write-Host ''
Write-Host 'This server listens only on this computer (127.0.0.1).' -ForegroundColor DarkGray
Write-Host 'Keep this window open while testing. Press Ctrl+C to stop.' -ForegroundColor Yellow
Write-Host ''

if (-not $NoBrowser) {
    Start-Process $Url
}

try {
    while ($true) {
        $Client = $Listener.AcceptTcpClient()
        try {
            $Stream = $Client.GetStream()
            $Reader = New-Object System.IO.StreamReader($Stream, [System.Text.Encoding]::ASCII, $false, 4096, $true)
            $RequestLine = $Reader.ReadLine()
            if ([string]::IsNullOrWhiteSpace($RequestLine)) { continue }

            while ($true) {
                $Line = $Reader.ReadLine()
                if ([string]::IsNullOrEmpty($Line)) { break }
            }

            $Parts = $RequestLine.Split(' ')
            if ($Parts.Length -lt 2) { continue }
            $Method = $Parts[0].ToUpperInvariant()
            $RawTarget = $Parts[1].Split('?')[0]
            $Decoded = [System.Uri]::UnescapeDataString($RawTarget)
            if ($Decoded -eq '/') { $Decoded = '/index.html' }

            $Relative = $Decoded.TrimStart('/').Replace('/', [System.IO.Path]::DirectorySeparatorChar)
            $Candidate = [System.IO.Path]::GetFullPath((Join-Path $RootFull $Relative))

            $Status = '200 OK'
            $Mime = 'text/plain; charset=utf-8'
            $Body = [byte[]]@()

            if (-not $Candidate.StartsWith($RootFull, [System.StringComparison]::OrdinalIgnoreCase)) {
                $Status = '403 Forbidden'
                $Body = [System.Text.Encoding]::UTF8.GetBytes('Forbidden')
            } elseif ([System.IO.Directory]::Exists($Candidate)) {
                $Index = Join-Path $Candidate 'index.html'
                if ([System.IO.File]::Exists($Index)) {
                    $Candidate = $Index
                    $Mime = Get-MimeType $Candidate
                    $Body = [System.IO.File]::ReadAllBytes($Candidate)
                } else {
                    $Status = '404 Not Found'
                    $Body = [System.Text.Encoding]::UTF8.GetBytes('Not found')
                }
            } elseif ([System.IO.File]::Exists($Candidate)) {
                $Mime = Get-MimeType $Candidate
                $Body = [System.IO.File]::ReadAllBytes($Candidate)
            } else {
                $Status = '404 Not Found'
                $Body = [System.Text.Encoding]::UTF8.GetBytes('Not found')
            }

            $HeaderText = "HTTP/1.1 $Status`r`nContent-Type: $Mime`r`nContent-Length: $($Body.Length)`r`nCache-Control: no-cache`r`nConnection: close`r`n`r`n"
            $Header = [System.Text.Encoding]::ASCII.GetBytes($HeaderText)
            $Stream.Write($Header, 0, $Header.Length)
            if ($Method -ne 'HEAD' -and $Body.Length -gt 0) {
                $Stream.Write($Body, 0, $Body.Length)
            }
            $Stream.Flush()
        } catch {
            # Ignore malformed browser requests and keep the local server alive.
        } finally {
            $Client.Close()
        }
    }
} finally {
    $Listener.Stop()
}
