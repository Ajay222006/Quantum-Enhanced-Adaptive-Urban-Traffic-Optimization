$ErrorActionPreference = 'Stop'

# Run from the project root in PowerShell.
$projectRoot = (Get-Location).Path
$sumoCandidates = @(
    'C:\Program Files (x86)\Eclipse\Sumo',
    'C:\Program Files\Eclipse\Sumo',
    'C:\Program Files\SUMO',
    'C:\Program Files (x86)\SUMO'
)
$sumoHome = $sumoCandidates | Where-Object { Test-Path (Join-Path $_ 'bin\sumo.exe') } | Select-Object -First 1

if (-not $sumoHome) {
    throw 'SUMO was not found. Install SUMO first, then run this script again.'
}

python -m pip install --upgrade pip
python -m pip install -r requirements.txt

$userPath = [Environment]::GetEnvironmentVariable('Path', 'User')
$sumoBin = Join-Path $sumoHome 'bin'
$pathEntries = @($userPath -split ';' | Where-Object { $_ })
if ($pathEntries -notcontains $sumoBin) {
    [Environment]::SetEnvironmentVariable('Path', (($pathEntries + $sumoBin) -join ';'), 'User')
}
[Environment]::SetEnvironmentVariable('SUMO_HOME', $sumoHome, 'User')
[Environment]::SetEnvironmentVariable('PYTHONPATH', $projectRoot, 'User')

# Apply the values to this PowerShell session too.
$env:SUMO_HOME = $sumoHome
$env:PYTHONPATH = $projectRoot
$env:Path = "$sumoBin;$env:Path"

Write-Host "SUMO_HOME=$env:SUMO_HOME"
Write-Host "PYTHONPATH=$env:PYTHONPATH"
& (Join-Path $sumoBin 'sumo.exe') --version
python -c "import numpy, traci, xgboost, sklearn, joblib; print('Python dependencies OK')"
Write-Host 'Setup complete. Open a new terminal for persistent environment variables.'
