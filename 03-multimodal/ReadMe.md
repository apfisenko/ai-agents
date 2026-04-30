# Проект бота с LLM (AIDD)

MVP-бот на Python 3.11: Telegram (long polling), ответы через **OpenRouter** или **локальный Ollama** (оба через OpenAI-совместимый API, `base_url` из env) с системным промптом из файла. Подробности целей и границ — в `docs/vision.md`, план итераций — в `docs/tasklist.md`.

## Текущее состояние MVP

| Итерация | Статус |
|----------|--------|
| Каркас, конфигурация, запуск в Telegram | готово |
| Диалог с моделью и история в памяти процесса | готово |
| Docker и compose | готово |
| Учёт текста/VLM, OpenRouter/Ollama в `.env`, голосовые (audio в LLM) | готово |

**Уже есть:** текстовое сообщение и **голосовое** (аудио в LLM через `input_audio`, см. `.env.example` и модель с поддержкой audio) → тот же учёт транзакций по истории из `SYSTEM_PROMPT_PATH`; фото чека → VLM; контекст по `chat_id` до перезапуска; `/start` сбрасывает историю; `/check_telegram` — связь с Telegram; прочие нетиповые сообщения — короткая подсказка; при ошибке LLM — нейтральный ответ; прокси `HTTPS_PROXY` / `HTTP_PROXY` (см. ниже); тот же `.env` для `uv run` и Docker Compose.

## Зависимости и запуск

- [uv](https://docs.astral.sh/uv/), Python **3.11** (см. `pyproject.toml`).
- Скопировать `.env.example` в `.env` и задать переменные (токен бота, **`OPENROUTER_API_KEY`** / URL / модели — OpenRouter или Ollama, см. раздел ниже), `LLM_MAX_COMPLETION_TOKENS`, путь к файлу системного промпта и т.д.).
- **Напрямую:** `uv sync` и `uv run python -m aidd` из **корня репозитория** (каталог с `pyproject.toml`).
- **macOS и Linux** — GNU Make в корне проекта:
  - `make install` — `uv sync`
  - `make run` — `uv run python -m aidd`
- **Windows** — PowerShell, скрипт `make.ps1` рядом с `Makefile`: `.\make.ps1 install` и `.\make.ps1 run`.

### Docker

Нужны **Docker Desktop** с **WSL2** и включённой интеграцией с вашим дистрибутивом (Settings → Resources → WSL integration). В WSL должен быть доступен **`docker`** и **`docker compose`** (проверка из PowerShell: `wsl -e docker version` и `wsl -e docker compose version` — без ошибки про недоступный daemon).

**Windows (PowerShell)** — цели Docker в `make.ps1` выполняют **`docker compose` через WSL**, с рабочим каталогом **корня репозитория** на диске Windows (`wsl --cd <корень> -e docker compose ...`). Отдельно ставить Docker в PATH Windows не требуется.

1. В корне проекта подготовьте `.env` (как для `uv run`), в том числе **`LLM_MAX_COMPLETION_TOKENS`** (см. `.env.example`). `SYSTEM_PROMPT_PATH=prompts/system.txt` в контейнере совпадает с образом.
2. **Прокси (и на хосте, и в Docker):** `HTTPS_PROXY` / `HTTP_PROXY` в `.env` — **один и тот же** сценарий: без прокси Telegram (и OpenRouter) часто недоступны. Из контейнера запрос к `127.0.0.1:ПОРТ` **автоматически идёт на прокси на Windows** (не на localhost внутри контейнера). Типичная ошибка: прокси на Windows слушает только `127.0.0.1` — с Docker bridge до него **нет** пути, пока не включите **Allow LAN** в VPN и/или **netsh portproxy** (см. раздел **Docker в WSL** ниже; подсказка команд: `.\make.ps1 docker-portproxy-hint`). Исключение: `AIDD_DOCKER_DIRECT_NETWORK` в `docker-compose` — только если у вас **в контейнере** к Telegram **уже** есть выход **без** прокси (например, другое сетевое окружение); тогда в `.env` прокси может оставаться для `uv run` на хосте.
3. Из PowerShell в этом каталоге:
   - `.\make.ps1 docker-build` — сборка образа
   - `.\make.ps1 docker-up` — `docker compose up --build`
   - `.\make.ps1 docker-down` — `docker compose down`  
   - `.\make.ps1 docker-ps` — `docker compose ps -a`
   - `.\make.ps1 docker-check` — `docker compose exec -T bot true`
   - `.\make.ps1 docker-windows-host-ip` — подсказка IP для `AIDD_WINDOWS_PROXY_HOST`
   - `.\make.ps1 docker-portproxy-hint` — шаблон netsh, если в Docker к прокси на Windows нет соединения
   - `.\make.ps1 docker-up-host` / `docker-down-host` — тот же compose + **`network_mode: host`** (если поддерживается вашим Docker; на части установок Docker Desktop + WSL2 недоступно)  
   Прервать foreground-запуск: `Ctrl+C`.

В `docker-compose` заданы `AIDD_DOCKER=1`, DNS `1.1.1.1` / `8.8.8.8`, `extra_hosts` для `host.docker.internal`. В контейнере для aiohttp принудительно **IPv4**. Обычно **нужен** тот же `HTTPS_PROXY` в `.env`, что и при `uv run` — иначе трафик из Docker не пойдёт в ту же сеть/VPN, что и приложения на Windows; альтернатива — [зеркалирование сети WSL](https://learn.microsoft.com/en-us/windows/wsl/networking#mirrored-mode-networking). В логах смотрите **«Детали: …»** при сетевых ошибках.

**macOS / Linux:** те же действия через `make docker-build`, `make docker-up`, `make docker-down`, `make docker-ps`, `make docker-check` (локальный `docker compose`).

**Вручную в терминале WSL** (по желанию): перейти в каталог проекта (`cd /mnt/c/...`) и вызвать `docker compose build` / `up --build` / `down`; для проверки — `docker compose ps -a` и `docker compose exec -T bot true`.

## Переменные окружения

Список обязательных имён и пример значений — в `.env.example` (скопировать в `.env`; секреты в репозиторий не класть, только пример).

**Обязательные параметры включают:** `TELEGRAM_BOT_TOKEN`, `OPENROUTER_API_KEY`, `LLM_MODEL`, `OPENROUTER_BASE_URL`, **`LLM_MAX_COMPLETION_TOKENS`** — целое **64–8192**, задаёт **`max_tokens`** для ответа модели (типично **1024**); `SYSTEM_PROMPT_PATH` и др. По желанию: `LOG_LEVEL`, `TELEGRAM_HTTP_TIMEOUT`, прокси (`HTTPS_PROXY` / `HTTP_PROXY`).

### OpenRouter и Ollama: как переключать

Один и тот же бинарник; провайдер задаётся **только переменными окружения** (в т.ч. через `docker compose` и `env_file: .env`).

1. **Имена из кода** (другие префиксы приложение **не подхватывает**): `OPENROUTER_BASE_URL`, `OPENROUTER_API_KEY`, `LLM_MODEL`, для фото чеков — **`LLM_VISION_MODEL`**, для **голосовых** при отличии от текста — **`LLM_AUDIO_MODEL`** (если пусты, берётся `LLM_MODEL`). Лимиты: при необходимости **`LLM_VISION_MAX_COMPLETION_TOKENS`**, **`LLM_AUDIO_MAX_COMPLETION_TOKENS`**. Не используйте `OPENAI_BASE_URL` / `OPENAI_API_KEY` / `MODEL_TEXT` / `MODEL_IMAGE`.
2. **Профиль OpenRouter:** как в комментариях `.env.example`: `OPENROUTER_BASE_URL=https://openrouter.ai/api/v1`, `OPENROUTER_API_KEY=<ключ>`, `LLM_MODEL` и при необходимости `LLM_VISION_MODEL` в формате OpenRouter (например `openai/gpt-4o-mini`).
3. **Профиль Ollama** (сервер с `ollama serve`, API на порту **11434**):  
   `OPENROUTER_BASE_URL=http://<IP_или_хост>:11434/v1`  
   `OPENROUTER_API_KEY=ollama` (или другая **непустая** заглушка — переменная обязательна при старте)  
   `LLM_MODEL` и `LLM_VISION_MODEL` — имена моделей как в Ollama (пример: `qwen2.5:7b-instruct`, `qwen3-vl:8b-instruct`). Для голосовых — при необходимости отдельная **`LLM_AUDIO_MODEL`** (модель с поддержкой аудио в chat); если поддерживается той же мультимоделью что и текст — переменную можно не задавать.
   С Docker: с контейнера должен быть достижим хост с Ollama (не `127.0.0.1` **внутри** контейнера, если Ollama на другой машине — используйте реальный IP/LAN; при Ollama на том же ПК что и Docker — см. сеть WSL/маршрутизацию).
4. **Переключение туда-обратно:** отредактировать `.env` (URL + ключ + имена моделей), **перезапустить** процесс (`uv run` / контейнер). В логах при старте строка вида `LLM: текст=…; голос=…; фото чеков=…` — должна совпасть с выбранными моделями.
5. **Проверка (чеклист):** после смены профиля — старт без ошибки конфига; сырой запрос к API (например `curl` на `<OPENROUTER_BASE_URL>/models` при типичном `…/v1` в base); в Telegram — текст, при необходимости **голосовое** (модель с audio input задана через `LLM_AUDIO_MODEL` или та же мультимодель в `LLM_MODEL`) и фото чека.

Подробные закомментированные примеры — в `.env.example`.

### Прокси и VPN

Если Telegram в браузере открывается через VPN, а бот **не** подключается к `api.telegram.org` (таймаут, `TelegramNetworkError`), в `.env` укажите **HTTP(S)-прокси** из настроек локального прокси (Clash и т.д.). Порт **к прокси** в сценарии Docker+WSL+`netsh` — см. **основной вариант 11301** в подразделе про `ClientProxyConnectionError` ниже; порт **реального** HTTP-прокси на Windows — **часто 1301** (это `connectport` в `netsh`).

- Пример, если используете перенос **11301 → 1301** на Windows: `HTTPS_PROXY=http://127.0.0.1:11301`  
- Без `netsh` и с прокси на одном **1301**: `HTTPS_PROXY=http://127.0.0.1:1301`  
- При необходимости: `HTTP_PROXY` так же.

Сессия в коде (`TrustEnvAiohttpSession`) и клиент OpenRouter читают стандартные переменные (`trust_env` в aiohttp / httpx).

#### `Request timeout` в Docker — что делать, если не помогает ни прокси, ни порт

Таймаут **~60 с** к `api.telegram.org` из контейнера значит: **маршрута нет** (не «мало времени»). `TELEGRAM_HTTP_TIMEOUT` в `.env` почти никогда не устраняет это.

1. **Запуск без Docker** (часто самый быстрый обход): в PowerShell в корне проекта `.\make.ps1 run` — тот же `.env`, сеть как у остальных программ на Windows.  
2. [Зеркалирование сети WSL2](https://learn.microsoft.com/en-us/windows/wsl/networking#mirrored-mode-networking) — тогда сеть WSL/ Docker ближе к хосту.  
3. `.\make.ps1 docker-up-host` — `network_mode: host`, если Docker у вас это поддерживает.  
4. Локальный HTTP-прокси + **`netsh` portproxy** (подраздел ниже) — пока порт с Docker до прокси реально не открыт, таймаут останется.

#### Docker: `Request timeout` к Telegram без `HTTPS_PROXY`

В логах: **Request timeout** при пустом `HTTPS_PROXY` — из контейнера **прямой** доступ к `api.telegram.org` у вас не проходит (блокировка/маршрут), тогда как на **хосте** с тем же прокси/VPN всё ок. Верните в `.env` **`HTTPS_PROXY=...`**. Дальше, если появится **ClientProxyConnectionError** — настройте **netsh portproxy** (следующий подраздел; **основной** сценарий: внешний **11301** и реальный прокси на **1301**).

#### Docker в WSL и ошибка `ClientProxyConnectionError … ('172.x.x.x', 1301)`

**Если `netsh` portproxy на Windows уже сделан, а в логе всё ещё `… host.docker.internal:PORT … Connect call failed ('172.17.0.1', PORT)`** (часто при **Docker** через WSL, `.\make.ps1 docker-up`):

- `host.docker.internal` в Linux указывает на **WSL/хост Linux** (у моста docker часто `172.17.0.1`), **не** на **Windows** с Clash/прокси на `127.0.0.1`.
- В **`.env`** задайте **`AIDD_WINDOWS_PROXY_HOST`**: выполните `.\make.ps1 docker-windows-host-ip` — в файл добавьте строку вида `AIDD_WINDOWS_PROXY_HOST=172.30.32.1` (у вас IP будет **свой**; это **Windows** с точки зрения WSL, первый `nameserver` в `/etc/resolv.conf` в WSL). Переменная **подменяет** `host.docker.internal` в `HTTPS_PROXY`, трафик пойдёт к **сети Windows**, где работает `netsh` portproxy.
- `netsh` portproxy (ниже) и при необходимости правило брандмауэра — **как и раньше**; без `AIDD_WINDOWS_PROXY_HOST` при Docker+WSL вы иногда **бьёте не в тот** хост.

**Если** в логе не `172.17.0.1` и `AIDD_WINDOWS_PROXY_HOST` не нужен, запрос из контейнера идёт к прокси на **хосте** (см. `AIDD_WINDOWS_PROXY_HOST` выше, не на `127.0.0.1` внутри контейнера). HTTP-прокси, слушающий **только** `127.0.0.1` на **Windows** без portproxy, с «внешнего» IP хоста не виден — отсюда `Connect call failed`.

**Вариант 1 (по возможности, без `netsh`):** в клиенте прокси (Clash и т.д.) — **Allow LAN** / прослушивание **0.0.0.0**, чтобы порт прокси принимал подключения не только с `127.0.0.1`.

**Вариант 2 (основной на Windows+Docker+WSL, если прокси не виден с Docker):** `netsh` **с двумя портами**: **внешний** (например **11301**) → **`127.0.0.1` + порт, где реально слушает Clash/прокси (часто 1301)**. Так **не** занимают `0.0.0.0:1301` на всей системе — реже ломается VPN, чем единый порт 1301 снаружи. В **`.env`**: `HTTPS_PROXY=http://127.0.0.1:11301` (и при Docker+WSL — **`AIDD_WINDOWS_PROXY_HOST`**, см. выше). PowerShell **от администратора**:

```text
netsh interface portproxy add v4tov4 listenaddress=0.0.0.0 listenport=11301 connectaddress=127.0.0.1 connectport=1301
netsh advfirewall firewall add rule name="AIDD proxy 11301" dir=in action=allow protocol=TCP localport=11301
```

**То же из проекта (PowerShell от администратора, имя правила в брандмауэре без пробелов: `AIDD-proxy-11301`):** `.\make.ps1 portproxy-up` — по умолчанию `-ListenPort 11301` и `-ConnectPort 1301`. Выключение: `.\make.ps1 portproxy-down` (тот же `-ListenPort`). Пример другого внешнего порта: `.\make.ps1 portproxy-up -ListenPort 11301 -ConnectPort 7890`. Ручные команды в разделе «Удаление» ниже остаются актуальны, если правила создавали вручную с именем `AIDD proxy 11301`, а не через `make.ps1`.

(Подставьте **1301**, если у вас другой **внутренний** порт прокси; внешний **11301** можно заменить на любой свободный, тогда в `.env` порт в URL должен совпадать с `listenport`.)

**Вариант 3 (один порт, если с VPN нет конфликта):** внешний порт = внутренний (**1301**). У части пользователей после `listenport=1301` **перестаёт работать VPN** — тогда используйте **вариант 2 (11301)**.

```text
netsh interface portproxy add v4tov4 listenaddress=0.0.0.0 listenport=1301 connectaddress=127.0.0.1 connectport=1301
netsh advfirewall firewall add rule name="AIDD proxy 1301" dir=in action=allow protocol=TCP localport=1301
```

**Проверка:** `netsh interface portproxy show all`

**Вариант 4:** запуск с **`.\make.ps1 docker-up-host`** (два compose-файла, `network_mode: host`), если ваш Docker это поддерживает.

#### Удаление добавленных правил `netsh` и брандмауэра

1. Список переносов: `netsh interface portproxy show all` — запомните **Адрес** и **Порт** в **левой** половине (столбец «слушаем»; для 11301: `0.0.0.0` и `11301`).
2. Удаление **переноса** (подставьте `listenport` вместо **11301**, если у вас 1301):

```text
netsh interface portproxy delete v4tov4 listenaddress=0.0.0.0 listenport=11301
```

Повторите для второго правила, если настраивали и **1301**, и **11301**. Снова: `netsh interface portproxy show all` — таблица должна быть пустой.
3. Удаление **правила брандмауэра** (имя — как при создании):

```text
netsh advfirewall firewall delete rule name="AIDD proxy 11301"
netsh advfirewall firewall delete rule name="AIDD proxy 1301"
```

(Удаляйте только те имена, которые вы создавали; лишние команды с несуществующим именем выдадут ошибку — это нормально.)

4. Команды выполняйте **от администратора**. После удаления **перезапустите** VPN/прокси при необходимости.

### Системный промпт (`SYSTEM_PROMPT_PATH`, `prompts/system.txt`)

В логах при старте: строка `System prompt: <путь> (N chars)` — так видно, **какой файл** прочитан и что конфиг **не** пустой. Если путь **не** тот, что в Docker: в `.env` задайте **`SYSTEM_PROMPT_PATH=prompts/system.txt`** (в образе путь к корню `/app` совпадает с репозиторием). **Абсолютный** путь `C:\...` в контейнере Linux **не** сработает. После смены файла **пересоберите** образ / перезапустите контейнер. Имя и роль в ответе задаёт **модель** по тексту `system` — при бесплатных/слабых моделях иногда игнорирование инструкций; проверьте в логах длину и путь, затем при необходимости смените `LLM_MODEL` в `.env`.

## Документация

| Файл | Содержание |
|------|------------|
| `docs/vision.md` | Техническое видение MVP, стек, конфиг |
| `docs/tasklist.md` | Итерации разработки |
| `.env.example` | Шаблон переменных окружения |
