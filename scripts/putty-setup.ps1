<#
  One-time setup on your Windows PC so that the dashboard's PuTTY tab and "SSH session" buttons open a dedicated PuTTY
  window per router.

    powershell -ExecutionPolicy Bypass -File scripts\putty-setup.ps1                        install (dashboard on localhost:8082)
    powershell -ExecutionPolicy Bypass -File scripts\putty-setup.ps1 -DryRun                show what it would do, change nothing
    powershell -ExecutionPolicy Bypass -File scripts\putty-setup.ps1 -Uninstall             remove everything it added
    powershell -ExecutionPolicy Bypass -File scripts\putty-setup.ps1 -Server http://<eve-vm>:8082 -JumpUser root

  What it adds (your Windows user only, HKCU, no administrator rights):
    1. One saved PuTTY session per router, named "OSPF <lab> <router>", from the dashboard's GET /api/putty:
       - simulation mode (docker-compose.demo.yml): "OSPF sim R1" .. "OSPF sim R4", straight to the backend's SSH
         servers on 127.0.0.1:2201-2204;
       - real lab: one per router of every lab (the shared lab and labs/NN_topic/), through the EVE-NG VM with the
         Windows OpenSSH client (ssh.exe -W), because the management addresses 192.168.99.x only exist inside the VM.
    2. A link handler "ospfputty:" that the PuTTY tab and the "SSH session" buttons use. It starts
       putty.exe -load "<that session>".
  Passwords are never stored: PuTTY asks for them (the PuTTY tab shows them).
  Run it again when you switch between simulation and the real lab, or after labs are added.
  Requires: PuTTY. For the real lab also the Windows OpenSSH client and key login from this PC to <JumpUser>@<eve-vm>.
#>
param(
    [string]$Server = "http://localhost:8082",
    [string]$JumpUser = "root",
    [string]$PuttyPath = "",
    [switch]$Uninstall,
    [switch]$DryRun
)
$ErrorActionPreference = "Stop"
$sessions = "HKCU:\Software\SimonTatham\PuTTY\Sessions"
$proto = "HKCU:\Software\Classes\ospfputty"
$hostKeys = "HKCU:\Software\SimonTatham\PuTTY\SshHostKeys"

function Enc([string]$name) { $name -replace ' ', '%20' }      # PuTTY stores the spaces of a session name as %20

function Remove-OspfSessions {
    $n = 0
    if (Test-Path $sessions) {
        Get-ChildItem $sessions | Where-Object { $_.PSChildName -like "OSPF%20*" } | ForEach-Object {
            if (-not $DryRun) { Remove-Item -LiteralPath $_.PSPath -Recurse -Force }
            $n++
        }
    }
    return $n
}

if ($Uninstall) {
    $n = Remove-OspfSessions
    if (Test-Path $hostKeys) {      # the simulated routers' host keys this script trusted (rsa2@2201:127.0.0.1 ...)
        (Get-Item $hostKeys).Property | Where-Object { $_ -match '^rsa2@22\d\d:127\.0\.0\.1$' } | ForEach-Object {
            if (-not $DryRun) { Remove-ItemProperty -LiteralPath $hostKeys -Name $_ }
        }
    }
    if (Test-Path $proto) { if (-not $DryRun) { Remove-Item -LiteralPath $proto -Recurse -Force }; Write-Host "removed the ospfputty: link handler" }
    $tail = if ($DryRun) { " (dry run: nothing changed)" } else { "" }
    Write-Host "removed $n PuTTY sessions$tail"
    return
}

if (-not $PuttyPath) {
    foreach ($c in @("$env:ProgramFiles\PuTTY\putty.exe", "${env:ProgramFiles(x86)}\PuTTY\putty.exe", "$env:LOCALAPPDATA\Programs\PuTTY\putty.exe")) {
        if (Test-Path $c) { $PuttyPath = $c; break }
    }
}
if (-not $PuttyPath -or -not (Test-Path $PuttyPath)) { throw "putty.exe not found. Install PuTTY or pass -PuttyPath <full path>." }
$launcher = Join-Path $PSScriptRoot "putty-launch.ps1"
if (-not (Test-Path $launcher)) { throw "putty-launch.ps1 must be next to this script." }

$info = Invoke-RestMethod -Uri "$Server/api/putty" -TimeoutSec 20
if (-not $info.enabled) { throw "The dashboard at $Server has SSH login to its simulated routers turned off (OSPF_SIM_SSH=false)." }
$list = @($info.sessions)
$needJump = @($list | Where-Object { $_.jump }).Count -gt 0
$sshCmd = ""
if ($needJump) {
    $ssh = Join-Path $env:SystemRoot "System32\OpenSSH\ssh.exe"
    if (-not (Test-Path $ssh)) { throw "The Windows OpenSSH client was not found at $ssh (Settings > Optional features > OpenSSH Client)." }
    # A 32-bit PuTTY (Program Files (x86)) sees C:\Windows\System32 as SysWOW64, where ssh.exe does not exist: it must use Sysnative.
    if ([Environment]::Is64BitOperatingSystem -and $PuttyPath -like "*(x86)*") { $ssh = Join-Path $env:SystemRoot "Sysnative\OpenSSH\ssh.exe" }
    $sshCmd = $ssh.Replace('\', '\\')      # PuTTY reads a doubled backslash in a proxy command as one backslash
}
Write-Host "putty:    $PuttyPath"
Write-Host "mode:     $($info.mode)"
if ($needJump) { Write-Host "jump:     $JumpUser@<eve-vm> (key login with $ssh)" }
Write-Host "routers:  $($list.Count)"

# sessions of the other mode would point at routers that are not there: replace every OSPF session
$old = Remove-OspfSessions
if ($old -and -not $DryRun) { Write-Host "replaced $old earlier OSPF sessions" }

$count = 0
foreach ($r in $list) {
    $name = "OSPF $($r.lab) $($r.router)"
    $count++
    $via = if ($r.jump) { " via $JumpUser@$($r.jump)" } else { "" }
    if ($DryRun) { Write-Host "  would create '$name' -> $($r.username)@$($r.host):$($r.port)$via"; continue }
    $key = Join-Path $sessions (Enc $name)
    New-Item -Path $key -Force | Out-Null
    # no UserName: PuTTY opens with "login as:" and then asks for the password (both shown on the PuTTY tab)
    $str = @{ HostName = $r.host; Protocol = "ssh"; WinTitle = "OSPF $($r.lab) $($r.router)  $($r.host):$($r.port)" }
    if ($r.jump) {
        $str.ProxyTelnetCommand = "$sshCmd -W %host:%port $JumpUser@$($r.jump)"
        $str.KEX = "dh-group14-sha1,dh-group1-sha1,WARN"; $str.Cipher = "aes,3des,WARN"; $str.HostKey = "rsa,WARN"   # what IOS 15.2's SSH server offers
    }
    foreach ($k in $str.Keys) { Set-ItemProperty -LiteralPath $key -Name $k -Value $str[$k] -Type String }
    Set-ItemProperty -LiteralPath $key -Name PortNumber -Value ([int]$r.port) -Type DWord
    if ($r.jump) {
        Set-ItemProperty -LiteralPath $key -Name ProxyMethod -Value 5 -Type DWord        # 5 = run a local command
        Set-ItemProperty -LiteralPath $key -Name ProxyLogToTerminal -Value 2 -Type DWord  # show proxy errors until the session starts
    } else {
        Set-ItemProperty -LiteralPath $key -Name ProxyMethod -Value 0 -Type DWord        # direct connection
        if ($info.putty_hostkey) {
            # trust the simulated routers' host key up front, so the first login has no security alert
            if (-not (Test-Path $hostKeys)) { New-Item -Path $hostKeys | Out-Null }     # never -Force: it would wipe the other trusted keys
            Set-ItemProperty -LiteralPath $hostKeys -Name "rsa2@$($r.port):$($r.host)" -Value $info.putty_hostkey -Type String
        }
    }
    Set-ItemProperty -LiteralPath $key -Name ScrollbackLines -Value 10000 -Type DWord
}

if (-not $DryRun) {
    New-Item -Path $proto -Force | Out-Null
    Set-Item -LiteralPath $proto -Value "URL:OSPF lab PuTTY session"
    Set-ItemProperty -LiteralPath $proto -Name "URL Protocol" -Value "" -Type String
    Set-ItemProperty -LiteralPath $proto -Name "PuttyPath" -Value $PuttyPath -Type String
    New-Item -Path "$proto\shell\open\command" -Force | Out-Null
    Set-Item -LiteralPath "$proto\shell\open\command" -Value "powershell.exe -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$launcher`" `"%1`""
}
if ($DryRun) { Write-Host "dry run: would create $count sessions and the ospfputty: link handler; nothing changed." }
else { Write-Host "done: $count PuTTY sessions and the ospfputty: link handler. Open the dashboard's PuTTY tab and click 'Open in PuTTY' (the browser asks once to allow the link)." }
