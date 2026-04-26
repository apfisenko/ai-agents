# Создаёт .venv_notebook_demo, ставит ipykernel и регистрирует ядро Jupyter.
# Путь к python.exe в kernel.json переписывается в короткий 8.3-формат (иначе
# сбой выбора ядра, если путь к проекту содержит не-ASCII).
# Требуется: Python 3.11+ (py -3.11 / py -3.12). Запуск из корня репозитория.
# Использование:  .\register_jupyter_kernel.ps1
$ErrorActionPreference = "Stop"
$KernelName = "ai-agents-notebook-demo"

function Get-BasePythonExe {
  # Предпочитаем 3.12, иначе 3.11. Не используем только «хвост» $LASTEXITCODE: явно смотрим вывод.
  $candidates = @("-3.12", "-3.11")
  foreach ($a in $candidates) {
    $lines = & py $a -c "import sys; assert sys.version_info >= (3, 11); print(sys.executable)" 2>$null
    if ($LASTEXITCODE -ne 0) { continue }
    $exe = ($lines | Select-Object -Last 1).ToString().Trim()
    if ($exe -and (Test-Path -LiteralPath $exe)) { return $exe }
  }
  throw "Не найден Python 3.11+. Установите с https://www.python.org/downloads/ или: winget install Python.Python.3.12"
}

function Get-ShortPath([string] $Path) {
  if (-not (Test-Path -LiteralPath $Path)) { return $Path }
  $item = Get-Item -LiteralPath $Path
  if ($item.PSIsContainer) {
    return (New-Object -ComObject Scripting.FileSystemObject).GetFolder($item.FullName).ShortPath
  }
  return (New-Object -ComObject Scripting.FileSystemObject).GetFile($item.FullName).ShortPath
}

$RepoRoot = $PSScriptRoot
$VenvDir = Join-Path $RepoRoot ".venv_notebook_demo"
$BasePython = Get-BasePythonExe

if (-not (Test-Path (Join-Path $VenvDir "Scripts\python.exe"))) {
  Write-Host "Создаю venv: $VenvDir  (база: $BasePython)"
  & $BasePython -m venv $VenvDir
}

$Python = Join-Path $VenvDir "Scripts\python.exe"
& $Python -c "import sys; assert sys.version_info >= (3, 11); sys.exit(0)" | Out-Null
$ver = & $Python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
$DisplayName = "Python $ver (ai-agents .venv_notebook_demo)"

Write-Host "Устанавливаю ipykernel (единственный обязательный пакет для ядра)…"
& $Python -m pip install -U pip ipykernel

Write-Host "Регистрирую ядро: $KernelName"
$kDir = Join-Path $env:APPDATA "jupyter\kernels\$KernelName"
if (Test-Path -LiteralPath $kDir) { Remove-Item -LiteralPath $kDir -Recurse -Force }
& $Python -m ipykernel install --user --name $KernelName --display-name $DisplayName
if ($LASTEXITCODE -ne 0) { throw "ipykernel install завершился с кодом $LASTEXITCODE" }

$kernelJson = Join-Path $kDir "kernel.json"
if (-not (Test-Path $kernelJson)) { throw "Не найден $kernelJson" }

$pyResolved = (Resolve-Path $Python).Path
$pyShort = Get-ShortPath $pyResolved
$j = Get-Content -LiteralPath $kernelJson -Raw -Encoding utf8 | ConvertFrom-Json
$j.argv[0] = $pyShort
($j | ConvertTo-Json -Depth 6) + "`n" | Set-Content -LiteralPath $kernelJson -Encoding utf8
Write-Host "argv[0] -> $pyShort"
Write-Host "Готово. В VS Code / Cursor выберите ядро: $DisplayName"
