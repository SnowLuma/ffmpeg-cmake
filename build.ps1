[CmdletBinding()]
param(
    [string]$Preset = 'windows-msvc',
    [ValidateSet('Build', 'Configure', 'Test', 'Install')][string]$Action = 'Build',
    [int]$Jobs = 0,
    [string]$Branch,
    [switch]$Bootstrap,
    [Parameter(ValueFromRemainingArguments = $true)][string[]]$CMakeArgs
)
$arguments = @("$PSScriptRoot/build.py", '--preset', $Preset, '--action', $Action.ToLower(), '--jobs', $Jobs)
if ($Branch) { $arguments += @('--branch', $Branch) }
if ($Bootstrap) { $arguments += '--bootstrap' }
& python @arguments -- @CMakeArgs
if ($LASTEXITCODE) { throw "Build failed with exit code $LASTEXITCODE" }
