$ErrorActionPreference = 'Stop'
$exePath = 'C:\RJ1\LanRemote-0.2.0-安装包\LanRemote-Windows.exe'
$reportPath = Join-Path $PSScriptRoot 'firewall-repair-result.txt'
try {
    if (!(Test-Path -LiteralPath $exePath -PathType Leaf)) { throw 'Expected LanRemote executable not found.' }
    $backup = & netsh advfirewall firewall show rule name=lanremote-windows verbose
    $backup | Out-File -LiteralPath (Join-Path $PSScriptRoot 'firewall-before.txt') -Encoding utf8
    # Modify only the observed public-profile TCP block for this exact executable.
    # Keep Windows Firewall on and retain all unrelated rules, including UDP.
    $result = & netsh advfirewall firewall set rule name=lanremote-windows dir=in profile=public protocol=TCP "program=$exePath" new action=allow localport=8765 remoteip=LocalSubnet edge=no
    if ($LASTEXITCODE -ne 0) { throw ($result -join "`n") }
    $after = & netsh advfirewall firewall show rule name=lanremote-windows verbose
    @('Repair succeeded: public-profile TCP 8765, LocalSubnet, exact LanRemote executable.', $result, $after) | Out-File -LiteralPath $reportPath -Encoding utf8
    exit 0
} catch {
    $_ | Out-File -LiteralPath $reportPath -Encoding utf8
    exit 1
}
