param([string]$Configuration = 'Release')
$ErrorActionPreference = 'Stop'
cmake -S $PSScriptRoot -B "$PSScriptRoot/build" -A x64
if ($LASTEXITCODE) { throw 'CMake configuration failed' }
cmake --build "$PSScriptRoot/build" --config $Configuration
if ($LASTEXITCODE) { throw 'Native build failed' }
ctest --test-dir "$PSScriptRoot/build" -C $Configuration --output-on-failure
if ($LASTEXITCODE) { throw 'Native tests failed' }
cmake --install "$PSScriptRoot/build" --config $Configuration --prefix "$PSScriptRoot/dist"
if ($LASTEXITCODE) { throw 'Runtime staging failed' }
