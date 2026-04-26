# Удаляет записи Python 3.9 из СИСТЕМНОГО (Machine) PATH, чтобы не стояли ПЕРЕД
# пользовательским Python 3.11. Требует: PowerShell «Запуск от имени администратора».
# После выполнения закройте и снова откройте терминалы и Cursor.
#Requires -RunAsAdministrator
$ErrorActionPreference = "Stop"

$mp = [Environment]::GetEnvironmentVariable("Path", "Machine")
$parts = $mp -split ';' | ForEach-Object { $_.Trim() } | Where-Object {
    $_ -and ($_.TrimEnd('\') -notmatch '(?i)Program Files\\Python39(\\Scripts)?$')
}
[Environment]::SetEnvironmentVariable("Path", ($parts -join ';'), "Machine")

Write-Host "Готово: из системного PATH убраны Program Files\Python39 и ...\Scripts."
Write-Host "Перезапустите PowerShell и выполните:  where.exe python"
Write-Host "Ожидается первая строка: ...\Python311\python.exe"
