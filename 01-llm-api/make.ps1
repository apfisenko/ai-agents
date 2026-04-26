#Requires -Version 5.1
# Аналог make для PowerShell: setup, run, clean, help
# Запуск из каталога 01-llm-api: .\make.ps1 <команда>

param(
    [Parameter(Position = 0)]
    [string] $Command = "help"
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

function Show-Help {
    Write-Host "Доступные команды:"
    Write-Host "  .\make.ps1 setup  - Установить зависимости через uv"
    Write-Host "  .\make.ps1 run    - Запустить CLI бот"
    Write-Host "  .\make.ps1 clean  - Очистить временные файлы"
    Write-Host ""
    Write-Host "Создание .env: Copy-Item .env.example .env"
}

function Invoke-Setup {
    Write-Host "Установка зависимостей..."
    uv sync
    Write-Host "✓ Зависимости установлены"
    Write-Host ""
    Write-Host "Не забудьте создать .env файл на основе .env.example"
    Write-Host "  Copy-Item .env.example .env"
    Write-Host "  # затем отредактируйте .env и добавьте ваш API ключ"
}

function Invoke-Run {
    if (-not (Test-Path -Path ".env" -PathType Leaf)) {
        Write-Host "❌ Файл .env не найден!"
        Write-Host "Скопируйте .env.example в .env и добавьте ваш API ключ:"
        Write-Host "  Copy-Item .env.example .env"
        exit 1
    }
    uv run python src/bot.py
}

function Invoke-Clean {
    Write-Host "Очистка временных файлов..."
    Get-ChildItem -Path . -Recurse -Directory -Filter "__pycache__" -ErrorAction SilentlyContinue |
        ForEach-Object { Remove-Item -LiteralPath $_.FullName -Recurse -Force -ErrorAction SilentlyContinue }
    Get-ChildItem -Path . -Recurse -File -ErrorAction SilentlyContinue |
        Where-Object { $_.Extension -in @('.pyc', '.pyo', '.log') } |
        Remove-Item -Force -ErrorAction SilentlyContinue
    Write-Host "✓ Очистка завершена"
}

switch ($Command) {
    "setup" { Invoke-Setup }
    "run" { Invoke-Run }
    "clean" { Invoke-Clean }
    "help" { Show-Help }
    default {
        Write-Host "Неизвестная команда: $Command" -ForegroundColor Red
        Write-Host ""
        Show-Help
        exit 1
    }
}
