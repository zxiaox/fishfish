param(
  [Parameter(Mandatory=$true)][ValidateSet('work-motivator','monty-hall')][string]$App,
  [Parameter(Mandatory=$true)][string]$Executable,
  [Parameter(Mandatory=$true)][string]$OutputDirectory
)
$ErrorActionPreference = 'Stop'
New-Item -ItemType Directory -Force -Path $OutputDirectory | Out-Null
$target = Join-Path $OutputDirectory "$App.exe"
if ((Resolve-Path $Executable).Path -ne (Resolve-Path $target).Path) { Copy-Item $Executable $target -Force }
$hash = (Get-FileHash $target -Algorithm SHA256).Hash.ToLowerInvariant()
[IO.File]::WriteAllText("$target.sha256", "$hash  $App.exe`n", [Text.Encoding]::ASCII)
$bundle = Join-Path $OutputDirectory "$App-portable"
New-Item -ItemType Directory -Force -Path $bundle | Out-Null
Copy-Item $target, "$target.sha256" -Destination $bundle -Force
@"
Extract this archive to a writable folder and launch $App.exe.
Settings are stored separately in %APPDATA%\fishfish\$App.
The application checks for updates and asks before installing them.
"@ | Set-Content -Encoding UTF8 (Join-Path $bundle 'README.txt')
$archive = Join-Path $OutputDirectory "$App-windows-x64-portable.zip"
Compress-Archive -Path (Join-Path $bundle '*') -DestinationPath $archive -Force
$zipHash = (Get-FileHash $archive -Algorithm SHA256).Hash.ToLowerInvariant()
[IO.File]::WriteAllText("$archive.sha256", "$zipHash  $App-windows-x64-portable.zip`n", [Text.Encoding]::ASCII)
