# Аналог Makefile для PowerShell. Примеры: .\make.ps1 install  |  .\make.ps1 run
param(
    [Parameter(Position = 0)]
    [ValidateSet("install", "run", "docker-build", "docker-up", "help")]
    [string] $Target = "help"
)
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

switch ($Target) {
    "install" { & uv sync }
    "run" { & uv run python -m aidd }
    "docker-build" { & docker compose build }
    "docker-up" { & docker compose up --build }
    "help" {
        Write-Host "Usage: .\make.ps1 <target>"
        Write-Host "  install       - uv sync"
        Write-Host "  run           - uv run python -m aidd"
        Write-Host "  docker-build  - docker compose build"
        Write-Host "  docker-up     - docker compose up --build"
    }
}
