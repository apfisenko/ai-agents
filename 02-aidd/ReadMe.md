# Проект бота с LLM (AIDD)

MVP-бот на Python 3.11: Telegram (long polling), ответы через **OpenRouter** (OpenAI-совместимый API) с системным промптом из файла. Подробности целей и границ — в `docs/vision.md`, план итераций — в `docs/tasklist.md`.

## Текущее состояние MVP

| Итерация | Статус |
|----------|--------|
| Каркас, конфигурация, запуск в Telegram | готово |
| Диалог с моделью и история в памяти процесса | готово |
| Docker и compose | готово |

**Уже есть:** текстовое сообщение → запрос к модели (`system` из файла по `SYSTEM_PROMPT_PATH` + история по `chat_id`) → ответ в чат; контекст сохраняется между репликами до перезапуска процесса; команда `/start` сбрасывает историю этого чата и показывает приветствие; `/check_telegram` — проверка связи с Telegram API; нетекстовые сообщения обрабатываются единообразно (короткая подсказка); при ошибке LLM пользователь видит короткое нейтральное сообщение без технических деталей; опционально прокси для клиента Telegram через `HTTPS_PROXY` / `HTTP_PROXY` (см. ниже).

## Docker

Нужны Docker и плагин Compose (на Windows удобно из WSL2, см. `docs/vision.md`). В корне проекта должен быть файл `.env` (как для локального запуска).

- `make docker-build` или `.\make.ps1 docker-build` — собрать образ
- `make docker-up` или `.\make.ps1 docker-up` — собрать и запустить контейнер (логи в терминале)

Переменные из `.env` передаются в контейнер через `docker-compose.yml`. Рабочая директория в образе — корень проекта, путь `SYSTEM_PROMPT_PATH=prompts/system.txt` из примера остаётся валидным.

## Зависимости и запуск

- [uv](https://docs.astral.sh/uv/), Python **3.11** (см. `pyproject.toml`).
- Скопировать `.env.example` в `.env` и задать переменные (токен бота, ключ OpenRouter, модель, `OPENROUTER_BASE_URL`, путь к файлу системного промпта и т.д.).
- **Напрямую:** `uv sync` и `uv run python -m aidd` (из корня каталога проекта `02-aidd`, где лежит `pyproject.toml`).
- **macOS и Linux** — GNU Make в корне проекта:
  - `make install` — `uv sync`
  - `make run` — `uv run python -m aidd`
  - `make docker-build` / `make docker-up` — см. раздел «Docker»
- **Windows** — PowerShell, скрипт `make.ps1` рядом с `Makefile`: `.\make.ps1 install`, `.\make.ps1 run`, при необходимости `.\make.ps1 docker-build` / `docker-up`.

## Переменные окружения

Список обязательных имён и смыслов — в `.env.example`. Секреты в репозиторий не класть, только пример.

### Прокси и VPN

Если Telegram в браузере открывается через VPN, а бот **не** подключается к `api.telegram.org` (таймаут, `TelegramNetworkError`), в `.env` укажите **HTTP(S)-прокси** из настроек VPN-клиента, например:

- `HTTPS_PROXY=http://127.0.0.1:1301`  
  Порт (например **1301**) — из раздела локального/HTTP-прокси в клиенте. При необходимости задайте ещё `HTTP_PROXY` так же.

Сессия в коде (`TrustEnvAiohttpSession`) читает стандартные переменные окружения (`trust_env` в aiohttp).

## Документация

| Файл | Содержание |
|------|------------|
| `docs/vision.md` | Техническое видение MVP, стек, конфиг |
| `docs/tasklist.md` | Итерации разработки |
| `.env.example` | Шаблон переменных окружения |
