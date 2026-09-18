param(
  [int]$StartPort = 8780,
  [switch]$NoBrowser
)

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$RootFull = [System.IO.Path]::GetFullPath($Root)
$Port = $StartPort
$Crlf = [string][char]13 + [string][char]10

function Get-LanIPv4 {
  return [System.Net.Dns]::GetHostAddresses([System.Net.Dns]::GetHostName()) |
    Where-Object {
      $_.AddressFamily -eq [System.Net.Sockets.AddressFamily]::InterNetwork -and
      -not [System.Net.IPAddress]::IsLoopback($_)
    } |
    Select-Object -First 1
}

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
    '.txt' { 'text/plain; charset=utf-8' }
    default { 'application/octet-stream' }
  }
}

function Send-Response($Stream, [int]$Code, [string]$Status, [string]$ContentType, [byte[]]$Body) {
  $HeaderText = 'HTTP/1.1 ' + $Code + ' ' + $Status + $Crlf +
    'Content-Type: ' + $ContentType + $Crlf +
    'Content-Length: ' + $Body.Length + $Crlf +
    'Cache-Control: no-cache' + $Crlf +
    'Connection: close' + $Crlf + $Crlf
  $Header = [System.Text.Encoding]::ASCII.GetBytes($HeaderText)
  $Stream.Write($Header,0,$Header.Length)
  if ($Body.Length -gt 0) { $Stream.Write($Body,0,$Body.Length) }
  $Stream.Flush()
}

function Send-Json($Stream, [object]$Value, [int]$Code = 200, [string]$Status = 'OK') {
  $Json = $Value | ConvertTo-Json -Depth 20 -Compress
  $Body = [System.Text.Encoding]::UTF8.GetBytes($Json)
  Send-Response $Stream $Code $Status 'application/json; charset=utf-8' $Body
}

function Send-Text($Stream, [string]$Text, [int]$Code = 400, [string]$Status = 'Bad Request') {
  Send-Response $Stream $Code $Status 'text/plain; charset=utf-8' ([System.Text.Encoding]::UTF8.GetBytes($Text))
}

function New-Event([string]$Type, [string]$ParticipantId, [string]$SectionId, [object]$Payload, [string]$ClientTime = $null) {
  $Event = [ordered]@{
    schema = 'org.openphysiologylab.classroom-event/v1'
    session_id = $SessionId
    server_time = [DateTime]::UtcNow.ToString('o')
    client_time = $ClientTime
    participant_id = $ParticipantId
    type = $Type
    section_id = $SectionId
    payload = $Payload
  }
  [void]$Events.Add([pscustomobject]$Event)
  ($Event | ConvertTo-Json -Depth 20 -Compress) | Add-Content -Path $EventLogPath -Encoding utf8
  return [pscustomobject]$Event
}

function Public-State {
  $ParticipantValues = @($Participants.Values | ForEach-Object {
    [pscustomobject]@{
      id = $_.id
      label = $_.label
      joined_at = $_.joined_at
      last_seen = $_.last_seen
      pretest_completed = $_.pretest_completed
      posttest_completed = $_.posttest_completed
    }
  })
  return [pscustomobject]@{
    schema = 'org.openphysiologylab.classroom-state/v1'
    session_id = $SessionId
    title = 'ECG Reference Lab classroom'
    join_code = $JoinCode
    student_url = $StudentUrl
    started_at = $StartedAt
    phase = $State.phase
    section = $State.section
    live_question_id = $State.live_question_id
    participants = $ParticipantValues
    questionnaire = [pscustomobject]@{
      path = 'questionnaires/ecg-reference-v0.1.json'
      id = 'ecg-reference-classroom-v0.1'
      version = '0.1.0'
    }
    opl_build = $BuildInfo
  }
}

$Listener = $null
while ($Port -lt ($StartPort + 20)) {
  try {
    $Listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Any,$Port)
    $Listener.Start()
    break
  } catch {
    if ($Listener) { try { $Listener.Stop() } catch {} }
    $Listener = $null
    $Port++
  }
}
if (-not $Listener) { throw 'Could not bind a classroom server port.' }

$LanIp = Get-LanIPv4
$HostForStudents = if ($LanIp) { $LanIp.IPAddressToString } else { '127.0.0.1' }
$BaseUrl = 'http://' + $HostForStudents + ':' + $Port
$SessionId = [Guid]::NewGuid().ToString('N')
$TeacherToken = [Guid]::NewGuid().ToString('N')
$JoinCode = Get-Random -Minimum 100000 -Maximum 999999
$StartedAt = [DateTime]::UtcNow.ToString('o')
$StudentUrl = $BaseUrl + '/classroom/student.html?room=' + $JoinCode
$TeacherUrl = 'http://127.0.0.1:' + $Port + '/classroom/teacher.html?teacher=' + $TeacherToken

$BuildInfo = $null
$BuildInfoPath = Join-Path $RootFull 'build-info.json'
if (Test-Path $BuildInfoPath) {
  try { $BuildInfo = Get-Content $BuildInfoPath -Raw | ConvertFrom-Json } catch {}
}

$State = [ordered]@{
  phase = 'pre'
  section = $null
  live_question_id = $null
}
$Participants = @{}
$Events = New-Object System.Collections.ArrayList
$SessionsDir = Join-Path $RootFull 'classroom_sessions'
New-Item -ItemType Directory -Force -Path $SessionsDir | Out-Null
$EventLogPath = Join-Path $SessionsDir ($SessionId + '.events.jsonl')
$ManifestPath = Join-Path $SessionsDir ($SessionId + '.manifest.json')

$Manifest = [ordered]@{
  schema = 'org.openphysiologylab.classroom-session/v1'
  session_id = $SessionId
  title = 'ECG Reference Lab classroom'
  join_code = $JoinCode
  started_at = $StartedAt
  questionnaire = [ordered]@{ id='ecg-reference-classroom-v0.1'; version='0.1.0' }
  reference_record = 'ECG-ID/Person_01/rec_1'
  opl_build = $BuildInfo
}
$Manifest | ConvertTo-Json -Depth 20 | Set-Content -Path $ManifestPath -Encoding utf8
[void](New-Event 'session_created' $null $null @{ join_code=$JoinCode } $null)

Write-Host ''
Write-Host 'OpenPhysiologyLab Classroom' -ForegroundColor Cyan
Write-Host '---------------------------'
Write-Host ('Teacher dashboard: ' + $TeacherUrl)
Write-Host ('Student phone URL: ' + $StudentUrl) -ForegroundColor Green
Write-Host ('Join code:         ' + $JoinCode) -ForegroundColor Yellow
Write-Host ('Event log:         ' + $EventLogPath)
Write-Host ''
Write-Host 'Teacher laptop and student phones must be on the same trusted network.' -ForegroundColor Yellow
Write-Host 'Windows Firewall may ask for permission. Do not expose this prototype to an untrusted/public network.' -ForegroundColor Yellow
Write-Host 'Press Ctrl+C after class to stop the server.' -ForegroundColor DarkGray
Write-Host ''

if (-not $NoBrowser) { Start-Process $TeacherUrl }

try {
  while ($true) {
    $Client = $Listener.AcceptTcpClient()
    try {
      $Stream = $Client.GetStream()
      $Reader = New-Object System.IO.StreamReader($Stream,[System.Text.Encoding]::UTF8,$false,8192,$true)
      $RequestLine = $Reader.ReadLine()
      if ([string]::IsNullOrWhiteSpace($RequestLine)) { continue }

      $Headers = @{}
      while ($true) {
        $Line = $Reader.ReadLine()
        if ([string]::IsNullOrEmpty($Line)) { break }
        $Colon = $Line.IndexOf(':')
        if ($Colon -gt 0) {
          $Headers[$Line.Substring(0,$Colon).Trim().ToLowerInvariant()] = $Line.Substring($Colon+1).Trim()
        }
      }

      $Parts = $RequestLine.Split(' ')
      if ($Parts.Length -lt 2) { continue }
      $Method = $Parts[0].ToUpperInvariant()
      $RawTarget = $Parts[1]
      $Uri = [System.Uri]('http://localhost' + $RawTarget)
      $Path = [System.Uri]::UnescapeDataString($Uri.AbsolutePath)
      $Query = [System.Web.HttpUtility]::ParseQueryString($Uri.Query)

      $BodyText = ''
      if ($Headers.ContainsKey('content-length')) {
        $Length = [int]$Headers['content-length']
        if ($Length -gt 0) {
          $Chars = New-Object char[] $Length
          $Read = 0
          while ($Read -lt $Length) {
            $N = $Reader.Read($Chars,$Read,$Length-$Read)
            if ($N -le 0) { break }
            $Read += $N
          }
          if ($Read -gt 0) { $BodyText = -join $Chars[0..($Read-1)] }
        }
      }

      $Payload = $null
      if ($BodyText) {
        try { $Payload = $BodyText | ConvertFrom-Json } catch {}
      }

      if ($Path -eq '/classroom/api/join' -and $Method -eq 'POST') {
        if (-not $Payload -or [string]$Payload.join_code -ne [string]$JoinCode) {
          Send-Text $Stream 'Invalid classroom join code.' 403 'Forbidden'
          continue
        }
        $Id = [Guid]::NewGuid().ToString('N')
        $Label = [string]$Payload.label
        if ($Label.Length -gt 40) { $Label = $Label.Substring(0,40) }
        $Now = [DateTime]::UtcNow.ToString('o')
        $Participants[$Id] = [pscustomobject]@{
          id=$Id; label=$Label; joined_at=$Now; last_seen=$Now; pretest_completed=$false; posttest_completed=$false
        }
        [void](New-Event 'participant_joined' $Id $null @{ label=$Label } $null)
        Send-Json $Stream @{ participant_id=$Id; label=$Label; session_id=$SessionId }
        continue
      }

      if ($Path -eq '/classroom/api/student/state' -and $Method -eq 'GET') {
        $Id = [string]$Query['participant_id']
        if (-not $Participants.ContainsKey($Id)) {
          Send-Text $Stream 'Participant not found.' 404 'Not Found'
          continue
        }
        $Participants[$Id].last_seen = [DateTime]::UtcNow.ToString('o')
        Send-Json $Stream @{ state=(Public-State) }
        continue
      }

      if ($Path -eq '/classroom/api/event' -and $Method -eq 'POST') {
        $Id = [string]$Payload.participant_id
        if (-not $Participants.ContainsKey($Id)) {
          Send-Text $Stream 'Participant not found.' 404 'Not Found'
          continue
        }
        $Participants[$Id].last_seen = [DateTime]::UtcNow.ToString('o')
        $Type = [string]$Payload.type
        if ($Type -eq 'pretest_completed') { $Participants[$Id].pretest_completed = $true }
        if ($Type -eq 'posttest_completed') { $Participants[$Id].posttest_completed = $true }
        [void](New-Event $Type $Id ([string]$Payload.section_id) $Payload.payload ([string]$Payload.client_time))
        Send-Json $Stream @{ ok=$true }
        continue
      }

      $IsTeacher = $Headers.ContainsKey('x-opl-teacher-token') -and $Headers['x-opl-teacher-token'] -eq $TeacherToken

      if ($Path -eq '/classroom/api/teacher/dashboard' -and $Method -eq 'GET') {
        if (-not $IsTeacher) { Send-Text $Stream 'Teacher token required.' 403 'Forbidden'; continue }
        Send-Json $Stream @{ state=(Public-State); events=@($Events) }
        continue
      }

      if ($Path -eq '/classroom/api/teacher/action' -and $Method -eq 'POST') {
        if (-not $IsTeacher) { Send-Text $Stream 'Teacher token required.' 403 'Forbidden'; continue }
        switch ([string]$Payload.type) {
          'set_phase' {
            $Allowed = @('pre','teach','post','closed')
            if ($Allowed -notcontains [string]$Payload.phase) { Send-Text $Stream 'Invalid phase.'; continue }
            $State.phase = [string]$Payload.phase
            [void](New-Event 'activity_changed' $null ([string]$State.section.id) @{ phase=$State.phase } $null)
          }
          'set_section' {
            $State.section = $Payload.section
            $State.phase = 'teach'
            [void](New-Event 'activity_changed' $null ([string]$State.section.id) @{ section=$State.section } $null)
          }
          'open_live_question' {
            $State.live_question_id = [string]$Payload.question_id
            [void](New-Event 'live_question_opened' $null ([string]$State.section.id) @{ question_id=$State.live_question_id } $null)
          }
          'close_live_question' {
            $Old = $State.live_question_id
            $State.live_question_id = $null
            [void](New-Event 'live_question_closed' $null ([string]$State.section.id) @{ question_id=$Old } $null)
          }
          default { Send-Text $Stream 'Unknown teacher action.'; continue }
        }
        Send-Json $Stream @{ ok=$true; state=(Public-State) }
        continue
      }

      if ($Path -eq '/classroom/api/export' -and $Method -eq 'GET') {
        if (-not $IsTeacher) { Send-Text $Stream 'Teacher token required.' 403 'Forbidden'; continue }
        Send-Json $Stream @{
          schema='org.openphysiologylab.classroom-export/v1'
          session_id=$SessionId
          manifest=$Manifest
          state=(Public-State)
          events=@($Events)
        }
        continue
      }

      if ($Method -ne 'GET' -and $Method -ne 'HEAD') {
        Send-Text $Stream 'Method not allowed.' 405 'Method Not Allowed'
        continue
      }

      if ($Path -eq '/') { $Path = '/classroom/teacher.html' }
      $Relative = $Path.TrimStart('/').Replace('/',[System.IO.Path]::DirectorySeparatorChar)
      $Candidate = [System.IO.Path]::GetFullPath((Join-Path $RootFull $Relative))
      if (-not $Candidate.StartsWith($RootFull,[System.StringComparison]::OrdinalIgnoreCase)) {
        Send-Text $Stream 'Forbidden.' 403 'Forbidden'
        continue
      }
      if ([System.IO.Directory]::Exists($Candidate)) { $Candidate = Join-Path $Candidate 'index.html' }
      if (-not [System.IO.File]::Exists($Candidate)) {
        Send-Text $Stream 'Not found.' 404 'Not Found'
        continue
      }
      $Bytes = [System.IO.File]::ReadAllBytes($Candidate)
      Send-Response $Stream 200 'OK' (Get-MimeType $Candidate) $Bytes
    } catch {
      try { Send-Text $Stream ('Server error: ' + $_.Exception.Message) 500 'Internal Server Error' } catch {}
    } finally {
      $Client.Close()
    }
  }
} finally {
  [void](New-Event 'session_closed' $null ([string]$State.section.id) @{ phase=$State.phase } $null)
  $Listener.Stop()
}
