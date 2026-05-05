# Аналог Makefile для PowerShell. Примеры: .\make.ps1 install  |  .\make.ps1 run
# netsh: .\make.ps1 portproxy-up   (с админа)  |  -ListenPort 11301 -ConnectPort 1301
param(
    [Parameter(Position = 0)]
    [ValidateSet("install", "run", "smoke-index", "dataset", "dataset-upload", "docker-build", "docker-up", "docker-down", "docker-up-host", "docker-down-host", "docker-ps", "docker-check", "docker-windows-host-ip", "docker-portproxy-hint", "portproxy-up", "portproxy-down", "help")]
    [string] $Target = "help",
    [int] $ListenPort = 11301,
    [int] $ConnectPort = 1301
)
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

function Assert-RunAsAdministrator {
    $p = [Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()
    if (-not $p.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        Write-Host "Нужен запуск PowerShell от имени администратора." -ForegroundColor Yellow
        exit 1
    }
}

# Имя правила брандмауэра без пробелов (удобно для netsh из PowerShell)
function Get-AiddFirewallRuleName { param([int] $P) return "AIDD-proxy-$P" }

function Invoke-DockerComposeViaWsl {
    param(
        [Parameter(Mandatory)]
        [string[]] $ComposeArguments
    )
    $repoRoot = (Resolve-Path -LiteralPath $PSScriptRoot).Path
    # Docker Desktop: CLI в WSL-дистрибутиве; каталог — корень репозитория на диске Windows.
    & wsl.exe --cd $repoRoot -e docker @ComposeArguments
}

switch ($Target) {
    "install" { & uv sync }
    "run" { & uv run python -m aidd }
    "smoke-index" { & uv run python -m aidd.smoke_index }
    "dataset" { & uv run python -m aidd.dataset_synthesizer synthesize }
    "dataset-upload" { & uv run python -m aidd.dataset_synthesizer upload }
    "docker-build" { Invoke-DockerComposeViaWsl -ComposeArguments @("compose", "build") }
    "docker-up" { Invoke-DockerComposeViaWsl -ComposeArguments @("compose", "up", "--build") }
    "docker-down" { Invoke-DockerComposeViaWsl -ComposeArguments @("compose", "down") }
    "docker-up-host" {
        Invoke-DockerComposeViaWsl -ComposeArguments @(
            "compose", "-f", "docker-compose.yml", "-f", "docker-compose.host-network.yml", "up", "--build"
        )
    }
    "docker-down-host" {
        Invoke-DockerComposeViaWsl -ComposeArguments @(
            "compose", "-f", "docker-compose.yml", "-f", "docker-compose.host-network.yml", "down"
        )
    }
    "docker-ps" { Invoke-DockerComposeViaWsl -ComposeArguments @("compose", "ps", "-a") }
    "docker-check" { Invoke-DockerComposeViaWsl -ComposeArguments @("compose", "exec", "-T", "bot", "true") }
    "docker-windows-host-ip" {
        Write-Host "IP Windows для AIDD_WINDOWS_PROXY_HOST (первый nameserver в WSL /etc/resolv.conf):"
        $ip = (& wsl.exe -e awk '/^nameserver/ {print $2; exit}' /etc/resolv.conf 2>$null)
        if ([string]::IsNullOrWhiteSpace($ip)) {
            Write-Host "Не удалось выполнить wsl. В WSL: awk '/^nameserver/ {print `$2; exit}' /etc/resolv.conf" -ForegroundColor Yellow
            exit 1
        }
        $ip = $ip.Trim()
        Write-Host $ip
        Write-Host "Добавьте в .env: AIDD_WINDOWS_PROXY_HOST=$ip"
    }
    "help" {
        Write-Host "Usage: .\make.ps1 <target>"
        Write-Host "  install       - uv sync"
        Write-Host "  run           - uv run python -m aidd"
        Write-Host "  smoke-index   - uv run python -m aidd.smoke_index (RAG-индексация, см. .env.example)"
        Write-Host "  dataset       - синтез datasets/05-rag-qa-dataset.json (OPEN_*, LLM_*; vision §10)"
        Write-Host "  dataset-upload - выгрузка JSON в LangSmith (LANGSMITH_API_KEY, LANGSMITH_DATASET_NAME)"
        Write-Host "  docker-build  - wsl: docker compose build (from repo root)"
        Write-Host "  docker-up     - wsl: docker compose up --build"
        Write-Host "  docker-down   - wsl: docker compose down"
        Write-Host "  docker-up-host   - compose + host network (см. ReadMe)"
        Write-Host "  docker-down-host - остановка того же стека"
        Write-Host "  docker-ps     - wsl: docker compose ps -a (state of containers)"
        Write-Host "  docker-check  - wsl: docker compose exec -T bot true (exit 0 if bot is up)"
        Write-Host "  docker-windows-host-ip - IP Windows для AIDD_WINDOWS_PROXY_HOST (Docker в WSL)"
        Write-Host "  docker-portproxy-hint   - шаблон netsh, если с Docker к прокси на Windows нет соединения"
        Write-Host "  portproxy-up            - netsh: включить 0.0.0.0:ListenPort -> 127.0.0.1:ConnectPort + брандмауэр (админ)"
        Write-Host "  portproxy-down          - netsh: выключить то же (удаление правил, админ); см. -ListenPort"
    }
    "portproxy-up" {
        Assert-RunAsAdministrator
        $name = Get-AiddFirewallRuleName -P $ListenPort
        Write-Host "Добавляю: listen 0.0.0.0:$ListenPort -> 127.0.0.1:$ConnectPort, брандмауэр: $name (по умолчанию -ListenPort 11301 -ConnectPort 1301)"
        & netsh interface portproxy add v4tov4 listenaddress=0.0.0.0 listenport=$ListenPort connectaddress=127.0.0.1 connectport=$ConnectPort
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
        & netsh advfirewall firewall add rule "name=$name" dir=in action=allow protocol=TCP "localport=$ListenPort"
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
        Write-Host "Готово. netsh interface portproxy show all"
    }
    "portproxy-down" {
        Assert-RunAsAdministrator
        $name = Get-AiddFirewallRuleName -P $ListenPort
        Write-Host "Удаляю: portproxy 0.0.0.0:$ListenPort, правило брандмауэра `"$name`""
        $prev = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        & netsh interface portproxy delete v4tov4 listenaddress=0.0.0.0 listenport=$ListenPort
        if ($LASTEXITCODE -ne 0) { Write-Host "portproxy delete: код $LASTEXITCODE (правило могло отсутствовать)" -ForegroundColor DarkYellow }
        & netsh advfirewall firewall delete rule "name=$name"
        if ($LASTEXITCODE -ne 0) { Write-Host "firewall delete: код $LASTEXITCODE (если правило вручную называли иначе — удалите вручную)" -ForegroundColor DarkYellow }
        $ErrorActionPreference = $prev
        Write-Host "Проверка: netsh interface portproxy show all"
    }
    "docker-portproxy-hint" {
        Write-Host "1) Windows (PowerShell/CMD + админ). Если VPN ломается на порту 1301 — внешний порт 11301, в .env HTTPS_PROXY=...11301, connect — на реальный 1301:`n"
        Write-Host 'netsh interface portproxy add v4tov4 listenaddress=0.0.0.0 listenport=11301 connectaddress=127.0.0.1 connectport=1301'
        Write-Host 'netsh advfirewall firewall add rule name="AIDD proxy 11301" dir=in action=allow protocol=TCP localport=11301'
        Write-Host "`nИли один внешний порт = реальный порт Clash (1301), если с VPN нет конфликта:`n"
        Write-Host 'netsh interface portproxy add v4tov4 listenaddress=0.0.0.0 listenport=1301 connectaddress=127.0.0.1 connectport=1301'
        Write-Host 'netsh advfirewall firewall add rule name="AIDD proxy 1301" dir=in action=allow protocol=TCP localport=1301'
        Write-Host "`nПроверка: netsh interface portproxy show all"
        Write-Host "`n2) Docker через WSL: если в ошибке 172.17.0.1:PORT — host.docker.internal = Linux, не Windows. В .env:"
        $ip = (& wsl.exe -e awk '/^nameserver/ {print $2; exit}' /etc/resolv.conf 2>$null)
        if (-not [string]::IsNullOrWhiteSpace($ip)) {
            Write-Host "   AIDD_WINDOWS_PROXY_HOST=$($ip.Trim())"
        } else {
            Write-Host "   Выполните: .\make.ps1 docker-windows-host-ip — и добавьте в .env строку AIDD_WINDOWS_PROXY_HOST=..."
        }
        Write-Host "`n3) Удаление: netsh interface portproxy delete v4tov4 listenaddress=0.0.0.0 listenport=11301   (и/или 1301)"
        Write-Host "   netsh advfirewall firewall delete rule name=`"AIDD proxy 11301`""
        Write-Host "Подробнее: ReadMe (удаление netsh, прокси 11301, ClientProxyConnectionError)"
    }
}
