$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$vendor = Join-Path $root 'vendor'
$target = Join-Path $vendor 'project1-boptest'
if (Test-Path (Join-Path $target '.git')) {
  git -C $target fetch --tags --depth 1 origin v0.9.0
  git -C $target checkout --detach 9b1610bf7a108826bb3d22c72bffd2d71d7bb0a9
} else {
  New-Item -ItemType Directory -Force -Path $vendor | Out-Null
  git clone --depth 1 --branch v0.9.0 https://github.com/ibpsa/project1-boptest.git $target
}
Write-Output "Pinned BOPTEST v0.9.0: $(git -C $target rev-parse HEAD)"
