$ErrorActionPreference = 'Stop'
$repoPath = $PSScriptRoot
$desktopPath = [Environment]::GetFolderPath('Desktop')
$shortcutShell = New-Object -ComObject WScript.Shell
foreach ($entry in @(@('BLE Tracker Search (Bluetooth + SDR)', 'start_tracker.cmd'), @('Sniff SDR BLE (Wireshark)', 'sniff_sdr.cmd'))) {
    $shortcutPath = Join-Path $desktopPath ($entry[0] + '.lnk')
    $shortcut = $shortcutShell.CreateShortcut($shortcutPath)
    $shortcut.TargetPath = Join-Path $repoPath $entry[1]
    $shortcut.WorkingDirectory = $repoPath
    $shortcut.Description = $entry[0]
    $shortcut.Save()
}
Write-Output 'Created the app and SDR Wireshark shortcuts. Existing computer-Bluetooth shortcuts are unchanged.'
