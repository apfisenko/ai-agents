# Отчёт по проекту

## Название и краткое описание

**Название:** проект Telegram-бота с LLM и RAG (пакет `aidd`).

**Описание:** асинхронный бот на **aiogram 3.x** (long polling), который ведёт текстовый диалог и отвечает через **LangChain RAG**: трансформация запроса с учётом истории, retrieval топ-K из **`InMemoryVectorStore`**, генерация ответа LLM по контексту и истории. Знания берутся из локальных файлов в `data/` (PDF и JSON по перечню в `docs/vision.md`). История диалога и векторный индекс живут в памяти процесса.

## Вариант

**AIDD** — см. заголовок и содержание `ReadMe.md` (не упрощённый «Лайт»).

## Реализованные возможности (чеклист)

- [x] Запуск бота, конфигурация из `.env`, валидация обязательных переменных при старте
- [x] Диалог с LLM через OpenRouter (OpenAI-совместимый API); системный промпт из файла (`SYSTEM_PROMPT_PATH`)
- [x] История по `chat_id` в памяти как **LangChain messages** (`HumanMessage` / `AIMessage`)
- [x] Команда `/start` (приветствие, сброс истории чата)
- [x] `/check_telegram` — проверка связи с Telegram API
- [x] Политика для нетекстовых сообщений (краткая подсказка)
- [x] Индексация: загрузка PDF (`PyPDFLoader`) и JSON, **`RecursiveCharacterTextSplitter`** для PDF, **`InMemoryVectorStore`**, **`OpenAIEmbeddings`**
- [x] Переиндексация при старте приложения, команды **`/index`** и **`/index_status`** (число чанков)
- [x] RAG-цепочка по смыслу **`rag_query_transform_chain`** из `data/naive-rag.ipynb` (`rag_chain.py`)
- [x] Параметр **`RETRIEVER_K`** для топ-K retriever
- [x] Docker / Docker Compose, Makefile и `make.ps1`, документация по прокси и сети

## Стек и используемые модели

| Область | Выбор |
|--------|--------|
| Язык | Python 3.11 |
| Зависимости | uv (`pyproject.toml`, lock) |
| Telegram | aiogram 3.x, async, polling |
| RAG | LangChain (`langchain_core`, `langchain_openai`, `langchain_community`, `langchain_text_splitters`) |
| Векторное хранилище | `InMemoryVectorStore` |
| LLM (чат и при необходимости query transform) | Задаётся **`LLM_MODEL`** и опционально **`LLM_QUERY_TRANSFORM_MODEL`** в `.env`; типичный пример в `.env.example`: `openai/gpt-4o-mini` |
| Эмбеддинги | **`EMBEDDING_MODEL`** в `.env`; значение по умолчанию в коде: **`openai/text-embedding-3-small`** (`src/aidd/indexing.py`, см. также `AppConfig`) |
| Провайдер API | OpenRouter: **`OPEN_BASE_URL`**, **`OPEN_API_KEY`** |

## Эксперименты с чанкингом: параметры и выводы

| Контекст | Параметры | Заметки |
|----------|-----------|---------|
| Учебный пример в `data/naive-rag.ipynb` | `RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=0)` | Короткие чанки для демонстрации пайплайна на одном тексте |
| Прод-код `src/aidd/indexing.py` (PDF) | `chunk_size=1500`, `chunk_overlap=150` | Больше текста на чанк и перекрытие на границах; разделители: `"\n\n\n"`, `"\n\n"`, `"\n"`, `". "`, `" "`, `""`; `keep_separator=True` |
| JSON `sberbank_help_documents.json` | Чанкинг **не** применяется | Каждая запись с непустым `full_text` — один цельный `Document` |

**Выводы:** для PDF выбраны более крупные чанки и ненулевой overlap, чтобы реже рвать связный юридический/справочный текст и сохранять контекст между соседними фрагментами. Для JSON логическая единица уже задана записью справки — дополнительное дробление не используется.

## JSON: загрузка и `JSONLoader`

В проекте **не** используется класс **`JSONLoader`** из LangChain Community.

Реализация в **`load_json_documents` / `_load_json_help`** (`src/aidd/indexing.py`):

- файл читается целиком, парсинг через стандартный **`json.loads`**;
- ожидается **массив** объектов;
- для каждого объекта-словаря с непустым полем **`full_text`** создаётся один **`Document`**;
- в **`metadata`** попадают как минимум `source` (имя файла), `index` (позиция в массиве), при наличии — `url`, `category`.

Такой подход проще для фиксированной схемы файла из `docs/vision.md` и не требует jq-схемы `JSONLoader`.

## Сравнение эмбеддингов

| Где | Модель |
|-----|--------|
| Пример в `data/naive-rag.ipynb` (сборка vector store) | `openai/text-embedding-3-large` |
| Дефолт в приложении и комментарий в `.env.example` | `openai/text-embedding-3-small` |

В репозитории **нет** формализованных замеров (precision@k, nDCG и т.п.) или таблицы прогонов на одном и том же наборе запросов.

**Практический вывод:** для MVP по умолчанию зафиксирована **`text-embedding-3-small`** — меньше стоимость и нагрузка при сохранении возможности сменить модель через **`EMBEDDING_MODEL`**. **`text-embedding-3-large`** остаётся референсом из ноутбука и опцией для экспериментов при необходимости более «тяжёлых» эмбеддингов.
