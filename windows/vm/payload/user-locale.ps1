[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'

# Culture (formats) and the user input-language list are deliberately independent.
# Opt out of Windows' automatic culture changes on display-language changes.
Set-WinCultureFromLanguageListOptOut -OptOut $true
Set-Culture -CultureInfo 'de-DE'
Set-WinHomeLocation -GeoId 94
Set-WinUILanguageOverride -Language 'en-US'

$Desired = New-WinUserLanguageList -Language 'en-US'
$Desired[0].InputMethodTips.Clear()
[void]$Desired[0].InputMethodTips.Add('0409:00000409')
$Russian = New-WinUserLanguageList -Language 'ru-RU'
$Russian[0].InputMethodTips.Clear()
[void]$Russian[0].InputMethodTips.Add('0419:00000419')
$Desired.Add($Russian[0])
Set-WinUserLanguageList -LanguageList $Desired -Force
Set-WinDefaultInputMethodOverride -InputTip '0409:00000409'

# Read back the state from the current user; the audit must also check it after logon/reboot.
$actual = @(Get-WinUserLanguageList)
$tags = @($actual | ForEach-Object { $_.LanguageTag.ToLowerInvariant() })
$tips = @($actual | ForEach-Object { $_.InputMethodTips } | ForEach-Object { [string]$_ })
if ($tags.Count -ne 2 -or $tags[0] -ne 'en-us' -or $tags[1] -notin @('ru','ru-ru') -or
    @($tips | Where-Object { $_ -notin @('0409:00000409','0419:00000419') }).Count -gt 0 -or
    @($tips | Where-Object { $_ -eq '0409:00000409' }).Count -ne 1 -or
    @($tips | Where-Object { $_ -eq '0419:00000419' }).Count -ne 1) {
    throw "User language list did not converge: tags=$($tags -join ',') tips=$($tips -join ',')"
}
if (-not (Get-WinCultureFromLanguageListOptOut)) {
    throw 'Culture-from-language-list opt-out was not retained.'
}
