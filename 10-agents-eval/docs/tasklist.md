# План разработки (итерации)

План ведётся по **спринтам**. Детали требований — в [vision.md](vision.md).

---

## Спринт 1 — Telegram-бот и LLM без RAG (завершён)

Текущая продуктовая цель и содержание ответов — в [idea.md](idea.md) (RAG по материалам из `data/`). В спринте 1 диалог шёл **без RAG**; строка итерации 4 в таблице описывает **историческую** роль в `prompts/system.txt` до перехода на RAG — выравнивание с `idea.md` выполнено в **итерации 7** спринта 2.

### Прогресс

| № | Итерация | Статус |
|---|----------|--------|
| 1 | Каркас, конфигурация, старт в Telegram | ✅ Done |
| 2 | Диалог с моделью и памятью в процессе | ✅ Done |
| 3 | Упаковка и запуск в Docker | ✅ Done |
| 4 | Системный промпт под раннюю роль (путешествия; до смены идеи на RAG) | ✅ Done |

### Легенда статусов

| Иконка | Статус | Значение |
|--------|--------|----------|
| 📋 | Planned | Запланирован |
| 🚧 | In Progress | В работе |
| ✅ | Done | Завершён |

---

### Итерация 1 — Каркас, конфигурация, старт в Telegram

**Проверка:** бот запускается; в Telegram отрабатывает `/start`; нетекстовые сообщения ведут себя по единому правилу; при неполной конфигурации приложение не стартует с понятной ошибкой; логи идут в консоль.

- [x] Репозиторий: зависимости, точка входа, long polling
- [x] Загрузка настроек из окружения и пример `.env.example`
- [x] Логирование (уровень из env, без секретов в логах)
- [x] Команда `/start` и короткое приветствие
- [x] Единая политика для нетекстовых сообщений

---

### Итерация 2 — Диалог с моделью и памятью в процессе

**Проверка:** текстовое сообщение → ответ от LLM с учётом системного промпта из файла; несколько реплик подряд сохраняют контекст до перезапуска; при сбое API пользователь видит короткое нейтральное сообщение.

- [x] Файл системного промпта и подключение к запросу
- [x] Хранилище истории по `chat_id` только в памяти
- [x] Клиент OpenRouter (совместимый вызов chat completions)
- [x] Связка: новое сообщение → история → ответ → обновление истории
- [x] Обработка ошибок LLM для пользователя и логов

---

### Итерация 3 — Упаковка и запуск в Docker

**Проверка:** `docker compose` поднимает сервис; бот ведёт себя как при локальном `uv run`; переменные окружения подхватываются.

- [x] Dockerfile (Python 3.11, uv)
- [x] `docker-compose.yml` с одним сервисом приложения
- [x] Make-цели и дублирующие команды или скрипты для PowerShell

---

### Итерация 4 — Системный промпт под раннюю роль продукта

**Контекст:** в ходе спринта 1 в `prompts/system.txt` была зафиксирована роль **консультанта по путешествиям**; актуальная идея сервиса — **RAG-ассистент по справочным документам из `data/`** ([idea.md](idea.md)); промпт приведён к этой роли в **итерации 7** спринта 2.

- [x] Выделенный файл промпта и связка с конфигом
- [x] Правила приветствия и тона для выбранной тогда роли (переносимые в новый промпт при ит. 7)

---

## Спринт 2 — RAG на LangChain (Telegram) (завершён)

### Прогресс

| № | Итерация | Статус |
|---|----------|--------|
| 5 | Данные, чанки, эмбеддинги, InMemoryVectorStore | ✅ Done |
| 6 | Переиндексация: старт, `/index`, `/index_status` | ✅ Done |
| 7 | Цепочка query transform + retriever K + ответ; история в messages | ✅ Done |

---

### Итерация 5 — Данные, чанки, эмбеддинги, InMemoryVectorStore

**Цель:** загрузка источников из `data/` (PDF из §1 vision, `sberbank_help_documents.json`), разбиение на чанки, эмбеддинги через OpenRouter/OpenAI-совместимый клиент, сборка **`InMemoryVectorStore`**. Логика в отдельном модуле (например `indexing.py`), без обязательной связки с Telegram в этой итерации.

**Проверка:** из кода или временного скрипта/теста можно построить индекс и выполнить простой similarity search; число чанков соответствует ожиданиям для входных файлов.

**Smoke:** после `uv sync` — `make smoke-index` или `uv run python -m aidd.smoke_index` (`OPEN_API_KEY`, `OPEN_BASE_URL`; опционально `EMBEDDING_MODEL`). Нет PDF — только предупреждения в логе; достаточно JSON.

- [x] Зависимости LangChain + loaders для PDF и JSON
- [x] Конфиг путей к файлам (константы или env — минимально достаточное)
- [x] Построение `InMemoryVectorStore` после загрузки и сплита

---

### Итерация 6 — Переиндексация: старт, `/index`, `/index_status`

**Цель:** при **старте бота** — полная переиндексация; команда **`/index`** — то же; **`/index_status`** — ответ с **числом чанков**. Обработка ошибок индексации — по правилу, зафиксированному в vision §7.

**Проверка:** после деплоя/рестарта индекс заполнен; `/index_status` показывает актуальное число; `/index` пересобирает хранилище.

- [x] Вызов пайплайна индексации при старте приложения
- [x] Handlers для `/index` и `/index_status`
- [x] `RETRIEVER_K` и ключевые RAG-переменные в `.env.example`

---

### Итерация 7 — Цепочка как в naive-rag; интеграция в диалог

**Цель:** реализовать по смыслу **`rag_query_transform_chain`** из **`data/naive-rag.ipynb`**: query transformation с историей → retriever (**top-K** = `RETRIEVER_K`) → ответ LLM с контекстом и историей. **`ConversationStore`** хранит историю как **LangChain messages** (`HumanMessage` / `AIMessage`). Системный промпт привести к роли RAG-ассистента по [idea.md](idea.md).

**Проверка:** в Telegram уточняющие вопросы используют историю при retrieval; ответы опираются на контент из документов; K меняется через `.env`.

- [x] Модуль `rag_chain.py` (или эквивалент): сборка Runnable-цепочки
- [x] Перевод истории чата на `HumanMessage`/`AIMessage`; подстановка в цепочку
- [x] Замена «голого» chat completion на RAG-путь в handler текстовых сообщений
- [x] Обновление `prompts/system.txt` под RAG и предметную область документов

---

## Спринт 3 — Мониторинг и оценка качества RAG (ДЗ-5)

Цели и технические ограничения — в [vision.md](vision.md), раздел «Мониторинг, синтез датасетов и RAGAS».

### Прогресс

| № | Итерация | Статус |
|---|----------|--------|
| 8 | ДЗ-5: источники в ответе и рефакторинг RAG-цепочки | ✅ Done |
| 9 | ДЗ-5: трейсинг LangSmith через окружение | ✅ Done |
| 10 | ДЗ-5: синтез датасета, JSON, make dataset / dataset-upload | ✅ Done |
| 11 | ДЗ-5: оценка RAGAS, /evaluate_dataset, feedback в LangSmith | ✅ Done |

---

### Итерация 8 — ДЗ-5: источники в ответе и рефакторинг RAG-цепочки

**Цель:** RAG-цепочка возвращает **текст ответа и retrieved-документы** с метаданными (файл, страницы); при **`SHOW_SOURCES=true`** пользователь видит строку вида `📚 Источники: filename.pdf (стр. 1, 3, 5)`.

**Проверка:** с включённым флагом в `.env` после запроса в Telegram отображаются источники; без флага — только ответ; K и ретривер без дублирования логики в хендлере.

- [x] Рефакторинг `rag_chain` (или эквивалента): ответ + документы для форматирования
- [x] Конфиг **`SHOW_SOURCES`**, пример в `.env.example`
- [x] Форматирование блока источников в handler

---

### Итерация 9 — ДЗ-5: трейсинг LangSmith через окружение

**Цель:** задокументировать и зафиксировать в **`.env.example`** переменные **`LANGSMITH_*`**, достаточные для автоматического трейсинга LangChain **без доработки кода цепочки** (если этого достаточно для выбранных версий зависимостей).

**Проверка:** при заданных переменных прогоны RAG видны в проекте LangSmith; при отсутствии — бот работает как раньше.

- [x] Актуальный перечень переменных в `.env.example` и краткая опора на vision

---

### Итерация 10 — ДЗ-5: синтез датасета, JSON, make dataset / dataset-upload

**Цель:** модуль **`dataset_synthesizer.py`**: по 2 чанка с каждого PDF в `data/`, LLM-генерация Q&A по чанку, слияние с готовыми Q&A из JSON при наличии, сохранение в **`datasets/<имя из LANGSMITH_DATASET>.json`**, загрузка в LangSmith с **пропуском дубликатов**. Make-цели **`dataset`** и **`dataset-upload`**.

**Проверка:** `make dataset` создаёт/обновляет файл датасета; `make dataset-upload` отправляет набор в LangSmith без повторов при повторном запуске.

- [x] Зависимости: `langsmith`, `datasets` (и то, что нужно для синтеза), lock
- [x] Реализация синтеза и загрузки по vision
- [x] Цели `make dataset`, `make dataset-upload`

---

### Итерация 11 — ДЗ-5: оценка RAGAS, /evaluate_dataset, feedback в LangSmith

**Цель:** модуль **`evaluation.py`**; команда бота **`/evaluate_dataset`** — полный цикл оценки; метрики **faithfulness**, **answer_relevancy**, **answer_correctness**, **answer_similarity**, **context_recall**, **context_precision**; результаты — **feedback в LangSmith**. Модели RAGAS — **`RAGAS_LLM_MODEL`**, **`RAGAS_EMBEDDING_MODEL`**. Ориентир — раздел 5 в **`data/rag-evaluation-practice.ipynb`**.

**Проверка:** по команде в Telegram (или согласованному триггеру) прогон завершается, метрики попадают в LangSmith; конфигурация описана в `.env.example`.

- [x] Зависимость **`ragas`** (≥ 0.2.0), интеграция с OpenRouter / клиентом проекта
- [x] Handler **`/evaluate_dataset`** и вызов оценки
- [x] Выгрузка метрик как feedback в LangSmith

---

## Спринт 4 — Advanced RAG: гибрид, rerank, провайдеры (ДЗ-6)

Цели и ограничения — [vision.md](vision.md) (§1–2, §6–10, сводка). Референс: **`data/advanced-hybrid-rag.ipynb`** (Part 1 — hybrid, Part 2 — cross-encoder); трансформация запроса по истории — по **`data/naive-rag.ipynb`**.

### Прогресс

| № | Итерация | Статус |
|---|----------|--------|
| 12 | ДЗ-6: зависимости и конфигурация режимов и провайдеров | ✅ Done |
| 13 | ДЗ-6: индексация и hybrid retrieval (semantic + BM25) | ✅ Done |
| 14 | ДЗ-6: cross-encoder reranking и LCEL-цепочка с query transform | ✅ Done |
| 15 | ДЗ-6: RAGAS, эмбеддинги по провайдеру, `.env.example` и регрессия | ✅ Done |

---

### Итерация 12 — ДЗ-6: зависимости и конфигурация режимов и провайдеров

**Цель:** добавить в проект **`sentence-transformers`**, **`langchain-community`**, **`rank-bm25`** (uv / lock); расширить **`config.py`** и **`.env.example`**: **`RAG_RETRIEVAL_MODE`** (`semantic` | `hybrid` | `hybrid_rerank`), **`EMBEDDING_PROVIDER`** (`openai` | `huggingface`), **`EMBEDDING_MODEL`**, имена **`CHAT`/`LLM`** (как принято), **`CROSS_ENCODER_MODEL`**, раздельные **`SEMANTIC_K`**, **`BM25_K`**, **`HYBRID_*_WEIGHT`**, **`RERANK_*`**, **`RAGAS_EMBEDDING_PROVIDER`**, **`RAGAS_EMBEDDING_MODEL`**, **`RAGAS_LLM_MODEL`**; валидация при старте.

**Проверка:** приложение собирается; при минимальном наборе env для выбранного режима старт не падает; при отсутствии обязательных ключей — понятная ошибка.

- [x] Зависимости и lock
- [x] Конфиг и `.env.example` по vision §9
- [x] Валидация обязательных переменных

---

### Итерация 13 — ДЗ-6: индексация и hybrid retrieval (semantic + BM25)

**Цель:** **`indexing.py`**: построение **`InMemoryVectorStore`** с эмбеддингами выбранного провайдера; сохранение (или повторное получение при старте) **списка чанков** для **`BM25Retriever`**. Режимы **`semantic`** и **`hybrid`**: семантический retriever и **`EnsembleRetriever`** (веса из env), без rerank. Команды **`/index`**, **`/index_status`**, старт — согласованы с новым пайплайном.

**Проверка:** в режимах `semantic` и `hybrid` ответы в Telegram сохраняются; **`/index_status`** показывает число чанков; гибрид не дублирует несогласованный сплит.

- [x] Эмбеддинги OpenAI-совместимые / HF по конфигу
- [x] Чанки + векторное хранилище + BM25 на тех же документах
- [x] Режимы `semantic` и `hybrid` в ретривере

---

### Итерация 14 — ДЗ-6: cross-encoder reranking и LCEL-цепочка с query transform

**Цель:** режим **`hybrid_rerank`**: пул кандидатов → **`CrossEncoder`** → топ для контекста. **`rag_chain.py`**: сборка **LCEL** с **сохранением этапа query transformation по истории** (как в naive-rag); выход — **текст + документы** для **`SHOW_SOURCES`**; без дублирования логики в хендлере.

**Проверка:** переключение режимов через env меняет поведение; уточняющие вопросы по истории влияют на retrieval; источники при флаге — корректны после rerank.

- [x] Reranker и параметры `RERANK_*`
- [x] LCEL: transform → retrieve → [rerank] → LLM
- [x] Интеграция в handler без поломки диалога

---

### Итерация 15 — ДЗ-6: RAGAS, эмбеддинги по провайдеру, `.env.example` и регрессия

**Цель:** **`evaluation.py`**: инициализация эмбеддингов RAGAS из **`RAGAS_EMBEDDING_PROVIDER`** / **`RAGAS_EMBEDDING_MODEL`** (и LLM — как в vision); прогон **`/evaluate_dataset`** на текущей цепочке retrieval; документация примеров в **`.env.example`**;Smoke-проверка основных режимов (ручная или существующая make-цель — по KISS).

**Проверка:** оценка завершается для обоих провайдеров embeddings (или задокументирован минимально поддерживаемый набор); feedback в LangSmith при настроенном проекте.

- [x] RAGAS + провайдеры embeddings
- [x] Актуальный `.env.example` и комментарии к режимам
- [x] Регрессия: диалог, `/index`, `SHOW_SOURCES`, evaluate

---

## Спринт 5 — ReAct-агент банковского сервиса: инструменты `rag_search` и `convert_currency`

Цели и технические ограничения — [vision.md](vision.md) (§1, §5–10, сводка). Референсы: **`data/agent.ipynb`** (`create_agent`, обёртка tool), **`data/advanced-hybrid-rag.ipynb`** (retrieval). Принципы: **KISS**, **YAGNI**.

### Прогресс

| № | Итерация | Статус |
|---|----------|--------|
| 16 | Инструмент `rag_search` и контракт `sources` | ✅ Done |
| 17 | `create_agent` + `MemorySaver`, системный промпт, интеграция в Telegram | ✅ Done |
| 18 | Stream, логирование шагов, fallback, извлечение источников для `SHOW_SOURCES` | ✅ Done |
| 19 | RAGAS: async `evaluate_dataset`, `aevaluate`, уникальный `thread_id`, контексты из `page_content` | ✅ Done |
| **20** | **ДЗ-7 (домашняя): второй инструмент `convert_currency` для пересчёта валют** | ✅ Done |

---

### Итерация 16 — Инструмент `rag_search` и контракт `sources`

**Цель:** оформить текущий retriever (режимы `semantic` / `hybrid` / `hybrid_rerank` из конфига) как **LangChain tool** с явным описанием, аргументами и возвращаемым значением по [vision.md](vision.md) §8. Ответ инструмента — JSON **`{"sources": [...]}`** с полями **`source`**, **`page_content`** (полный текст), **`page`** (для PDF при наличии), сериализация с **`ensure_ascii=False`**. Логику построения retriever переиспользовать из существующих модулей, без дублирования.

**Проверка:** из кода можно вызвать tool с тестовой строкой запроса; в режимах из `.env` возвращаются непустые `sources` при наличии индекса; JSON парсится.

- [x] Модуль(и) tool + связь с фабрикой retrieval / `indexing`
- [x] Контракт полей совпадает с vision §8
- [x] Режим retrieval берётся из **`RAG_RETRIEVAL_MODE`** (без query transformation внутри tool)

---

### Итерация 17 — `create_agent` + `MemorySaver`, системный промпт, Telegram

**Цель:** точка входа диалога — агент, собранный через **`create_agent()`** из LangChain 1.0 с **`MemorySaver`**; **`thread_id`** согласован с **`chat_id`**. Системный промпт ([vision.md](vision.md) §8): роль банковского ассистента, **когда** вызывать `rag_search`, **few-shot** и подсказки по формулировке поисковых фраз. Хендлер текстовых сообщений вызывает агент вместо прежней LCEL-цепочки ответа.

**Проверка:** в Telegram агент отвечает; при вопросе по документам вызывается `rag_search` (видно по трейсу или логам на уровне шагов, если включено); история сохраняется в рамках чата до перезапуска.

- [x] Сборка модели (OpenRouter) и списка tools
- [x] `create_agent` + checkpointer
- [x] Обновление `prompts/system.txt` под агента и банковскую роль
- [x] Интеграция в `handlers` / `telegram_bot.py` без лишней логики в хендлере

---

### Итерация 18 — Stream, лог шагов, fallback, источники

**Цель:** в пути получения ответа использовать **`agent.stream(..., stream_mode="values")`**. Функция логирования шагов (без секретов). **`warning`**, если пришёл пустой **`AIMessage`** без **`tool_calls`**. **Обязательный fallback** текста пользователю при пустом финальном ответе. Для **`SHOW_SOURCES`**: из истории брать сообщения **после последнего `HumanMessage`** и собрать документы из всех **`ToolMessage`**, связанных с **`rag_search`**.

**Проверка:** при включённом `SHOW_SOURCES` блок источников относится только к текущему запросу; fallback срабатывает на искусственно пустом ответе (тест или мок).

- [x] `stream_mode="values"` и финальный текст для Telegram
- [x] Логирование итераций / предупреждение без tool_calls
- [x] Fallback и форматирование источников

---

### Итерация 19 — Оценка RAGAS под агента

**Цель:** **`evaluation.py`**: **`evaluate_dataset`** полностью **async**; внутри **`async def target`**, корректный **`aevaluate`**: **`experiment_results = await client.aevaluate(...)`**, затем **`async for result in experiment_results`**. Контексты для RAGAS — **`page_content`** из документов, собранных из ответов и вызовов **`rag_search`**. На **каждый** пример выдаётся **уникальный `thread_id`** (или эквивалент для памяти). Сохранить **`/evaluate_dataset`** и feedback в LangSmith при настроенном проекте.

**Проверка:** прогон на датасете завершается; метрики и контексты согласованы с vision §10; повторный прогон не смешивает диалоги разных строк датасета.

- [x] Async target и поток результатов `aevaluate`
- [x] Извлечение `page_content` для метрик
- [x] Изоляция чекпоинта по `thread_id` на запись датасета

---

### Итерация 20 — ДЗ-7 (домашняя): инструмент `convert_currency`

**Цель:** добавить второй LangChain-tool **`convert_currency(amount, from_currency, to_currency)`**, доступный из банковского агента в Telegram: приблизительный пересчёт суммы между валютами по коду **ISO 4217** (три буквы); источник курсов — один согласованный публичный HTTP-сервис **без** отдельного API-ключа в `.env`; в ответе пользователю — дисклеймер, что курс ориентировочный и не является курсом банка. Контракт JSON и связь с **`SHOW_SOURCES`** / RAGAS — [vision.md](vision.md) §8, §10. В **`prompts/system.txt`** — когда вызывать инструмент и **few-shot**: из долларов в рубли (например **100 USD → RUB**), из евро в доллары (например **50 EUR → USD**).

**Проверка:** в Telegram запрос вида «100 долларов в рублях» или «переведи 50 EUR в доллары» приводит к вызову `convert_currency` (трейс LangSmith или лог шага с инструментом), ответ содержит пересчёт и напоминание про ориентировочность; при сетевой ошибке — короткое сообщение пользователю из ответа инструмента, без падения бота.

- [x] Модуль **`tools/currency_convert_tool.py`**: `@tool`, нормализация кодов, **`httpx`** async, контракт `ok` / `rate` / `result` / `note` или `error`
- [x] Регистрация tool в **`bank_agent.py`** рядом с **`rag_search`**
- [x] Зависимость **`httpx`** в **`pyproject.toml`** (явная); после правок выполнить **`uv lock`** / **`uv sync`** у разработчика
- [x] **`prompts/system.txt`**: правила вызова и два примера (USD→RUB, EUR→USD)
- [x] Выравнивание **idea.md** / **vision.md** под второй инструмент

---

## Спринт 6 — MCP-сервер банка и интеграция в агента

Цели — [vision.md](vision.md) (§1, §5–6, §8, §13, сводка): подпроект **`mcp/mcp-bank-agent`** (FastMCP, **streamable HTTP**, порт **8000**), данные **`bank_products.json`**, инструменты **`search_products`**, **`currency_converter_mcp`** и **`loan_payment_mcp`**; в боте — **`langchain-mcp-adapters`**, **async** **`create_bank_agent`** / **`initialize_agent`**, **`await mcp_client.get_tools()`**, **graceful degradation**, обновление **`prompts/system.txt`** ( **`rag_search`** vs **`search_products`**; **`convert_currency`** vs **`currency_converter_mcp`**; когда **`loan_payment_mcp`**). Референс: **`data/agent-mcp.ipynb`**. Запуск: **`make run-mcp-bank`**, затем **`make run`**; дублирование в **`make.ps1`**.

### Прогресс

| № | Итерация | Статус |
|---|----------|--------|
| 21 | Подпроект **`mcp-bank-agent`**: **`bank_products.json`**, **`search_products`**, streamable HTTP | ✅ Done |
| 22 | Инструмент **`currency_converter_mcp`** (ЦБ РФ, конвертация любой→любой через RUB) | ✅ Done |
| 23 | Агент: MCP-клиент, async-инициализация, graceful degradation, системный промпт | ✅ Done |
| 24 | Корневой **`pyproject`**, **`Makefile`** / **`make.ps1`**, **`run-mcp-bank`**, порядок запуска | ✅ Done |
| **25** | **MCP: инструмент `loan_payment_mcp` (аннуитет), системный промпт** | ✅ Done |

---

### Итерация 21 — Подпроект MCP: данные и `search_products`

**Цель:** каталог **`mcp/mcp-bank-agent`** с собственным **`pyproject.toml`** (**uv**), запуск MCP-сервера (**FastMCP**) в режиме **streamable HTTP** на порту **8000** (дефолт). Файл **`mcp/mcp-bank-agent/data/bank_products.json`** — согласованный с публичной информацией с сайта банка набор карточек (вклады, кредиты, дебетовые/кредитные карты, счета и т.д.). Инструмент **`search_products`**: простой поиск/фильтрация по типам, названиям, описаниям, условиям, акциям и типовым полям (KISS: без лишней ORM).

**Проверка:** из клиента MCP или тестового вызова доступен **`search_products`**; ответ осмыслен для тестовых запросов; сервер слушает **8000**.

- [x] Структура подпроекта и зависимости (**uv**)
- [x] **`bank_products.json`** и реализация **`search_products`**
- [x] Точка входа сервера (streamable HTTP)

**Запуск из корня репозитория (ит. 24):** `make run-mcp-bank` или `.\make.ps1 run-mcp-bank`. Иначе локально: `cd mcp/mcp-bank-agent && uv sync && uv run mcp-bank-agent` — URL **`http://127.0.0.1:8000/mcp`**.

---

### Итерация 22 — `currency_converter_mcp`

**Цель:** второй инструмент MCP: **`currency_converter_mcp`** — запрос к **cbr-xml-daily.ru** (JSON), универсальная конвертация **любая валюта → любая** через **RUB** (две ступени), обработка ошибок сети и неизвестных кодов (краткий ответ агенту).

**Проверка:** конвертация USD↔EUR / USD↔KZT и т.п. согласована с курсами ЦБ на дату ответа API; при недоступности API — понятная ошибка в результате tool.

- [x] Клиент HTTP и разбор ответа API
- [x] Логика **via RUB** и граничные случаи (**RUB**↔**RUB**)

---

### Итерация 23 — Интеграция MCP в агента

**Цель:** в корневом приложении — зависимость **`langchain-mcp-adapters>=0.1.0`**, **`MultiServerMCPClient`**, сборка списка tools: **`rag_search`**, **`convert_currency`**, **`+ await mcp_client.get_tools()`** при успехе. **`create_bank_agent()`** и **`initialize_agent()`** — **`async def`**. При недоступности MCP: **logging.warning**, агент только с базовыми tools. **`prompts/system.txt`**: когда **`rag_search`**, когда **`search_products`**; когда **`currency_converter_mcp`**, когда **`convert_currency`**; короткие **few-shot** примеры вызовов MCP-инструментов (в духе **`data/agent-mcp.ipynb`**).

**Проверка:** с запущенным **`make run-mcp-bank`** в Telegram видны вызовы MCP-tools; без MCP бот стартует и отвечает с **`rag_search`** / **`convert_currency`**.

- [x] Async-фабрика агента и подключение MCP
- [x] Graceful degradation
- [x] Обновление системного промпта

---

### Итерация 24 — Сборка и запуск

**Цель:** цель **`make run-mcp-bank`** в корневом **Makefile** (запуск подпроекта через **uv**); дублирование в **`make.ps1`**. Документированный порядок: терминал 1 — MCP, терминал 2 — бот. При необходимости — минимальные переменные в **`.env.example`** для URL MCP (детали без дублирования vision).

**Проверка:** на чистой машине после **`uv sync`**: **`make run-mcp-bank`** поднимает сервер; **`make run`** подключается при правильном URL. Дополнительно: **`make check-mcp-bank`** / **`.\make.ps1 check-mcp-bank`** и команда **`/mcp_status`** в боте.

- [x] **`Makefile`** и **`make.ps1`** (`run-mcp-bank`, `check-mcp-bank`)
- [x] **`pyproject.toml`** корня: **`langchain-mcp-adapters`**
- [x] **`.env.example`** и **`aidd.mcp_health`** / **`/mcp_status`**

---

### Итерация 25 — MCP `loan_payment_mcp` и промпт агента

**Цель:** в **`mcp/mcp-bank-agent`** добавить инструмент **`loan_payment_mcp(principal, annual_rate_percent, term_months)`** — ориентировочный **аннуитетный** месячный платёж, сумма возврата и переплата по упрощённой формуле (без комиссий и страховок); ответ агенту — JSON (**`ok`** / поля платежей / **`note`** с дисклеймером). В **`prompts/system.txt`** — правила **когда** вызывать при вопросах про «сколько платить в месяц», платёж по кредиту при известной сумме, ставке и сроке (и когда **не** вызывать: нет данных, нужен именно текст договора); **три** few-shot-примера вызова MCP.

**Проверка:** при запущенном MCP инструмент виден клиентом; типовые значения (например 300000 ₽, 12%/год, 24 мес.) дают правдоподобный **`monthly_payment`**; ставка **0** даёт `principal / term_months`. Агент в промпте сориентирован на вызов по сценарию «посчитай платёж». **idea.md** / **vision.md** согласованы со списком MCP-инструментов (**`loan_payment_mcp`** не участвует в **`SHOW_SOURCES`** / RAGAS).

- [x] **`mcp_bank_agent`**: модуль расчёта и **`@mcp.tool` `loan_payment_mcp`** в **`server.py`**
- [x] **`prompts/system.txt`**: правила и три примера **`loan_payment_mcp`**
- [x] Выравнивание **vision.md** / **idea.md**

---

## Спринт 7 — Безопасность: чувствительные MCP-операции (`open_credit_card`, `open_deposit`), HITL, PII, rate limiting

Цели и ограничения — [vision.md](vision.md) (§8, §12, сводка). Референс потока с interrupt: **`data/agent-guards-demo.ipynb`** (паттерн **`run_turn_agent`**, **`HumanInTheLoopMiddleware`**). Принципы: **KISS**, **YAGNI** — только **Accept** / **Reject** для HITL, без **edit**.

### Прогресс

| № | Итерация | Статус |
|---|----------|--------|
| 26 | MCP: инструмент **`open_credit_card`** (мок, контракт JSON) | ✅ Done |
| 27 | Агент: HITL для **`open_credit_card`**, **`run_turn_agent`**, промпт и MCP-клиент | ✅ Done |
| 28 | Telegram: inline **Accept** / **Reject**, resume, снятие клавиатуры | ✅ Done |
| 29 | PII-маскирование исходящих сообщений и политика логов | ✅ Done |
| 30 | Rate limiting по **`chat_id`**, **`.env.example`**, **`make.sh`** | ✅ Done |
| 31 | Лимит **обращений к агенту** (`ainvoke_turn`) на **`chat_id`** за окно времени | ✅ Done |
| 32 | MCP **`open_deposit`**, HITL и Telegram (общие Accept/Reject), промпт, vision/idea | 🚧 In Progress |

---

### Итерация 26 — MCP `open_credit_card`

**Цель:** в **`mcp/mcp-bank-agent`** добавить **`open_credit_card`** — мок открытия кредитной карты: логировать факт вызова без PAN в открытом виде; вернуть JSON с **`ok`**, полным номером карты (без маскирования в теле ответа инструмента), сроком действия и минимально необходимыми полями (**KISS**). Описание инструмента для LLM — явное «эмуляция».

**Проверка:** при запущенном MCP клиент видит инструмент; тестовый вызов возвращает валидный JSON; лог сервера не содержит полный PAN.

- [x] Реализация **`open_credit_card`** в подпроекте MCP
- [x] Выравнивание **vision.md** / **idea.md** при необходимости после интеграции (если контракт уточняли в коде)

---

### Итерация 27 — Агент: middleware и паттерн `run_turn_agent`

**Цель:** подключить **`HumanInTheLoopMiddleware`** с **`interrupt_on`** только для **`open_credit_card`**; переписать функцию «хода» агента по образцу **`run_turn_agent`** из **`data/agent-guards-demo.ipynb`** (streaming, **`__interrupt__`**, возврат interrupt наружу, **resume** с **`Command`**). Обновить **`prompts/system.txt`**: когда вызывать **`open_credit_card`**, инструкции и **few-shot** примеры вызова MCP-инструментов (включая новый). Без реализации ветки **edit**.

**Проверка:** в изолированном тесте или логах видно остановку перед вызовом **`open_credit_card`** и продолжение после approve/reject (после ит. 28 — через Telegram).

- [x] Middleware и сборка **`create_agent`**
- [x] Модуль/функция хода с interrupt + resume (модульная организация)
- [x] **`prompts/system.txt`**

---

### Итерация 28 — Telegram: кнопки HITL

**Цель:** при interrupt показывать пользователю текст с **деталями операции** и inline-кнопки **Accept** и **Reject**; по callback формировать **resume** агента; после нажатия **убрать клавиатуру** у сообщения (**edit_reply_markup**); защита от повторного нажатия — по возможности **KISS** (игнор или идемпотентность).

**Проверка:** сценарий открытия карты доходит до подтверждения; Accept приводит к успешному ответу MCP; Reject — к корректному отказу без вызова MCP; кнопки исчезают после выбора.

- [x] Callback-хендлер и связка с **`run_turn`/resume**
- [x] UX сообщения подтверждения

---

### Итерация 29 — PII-маскирование

**Цель:** маскировать PAN (минимум) в **исходящих** текстах Telegram; не логировать PAN открытым текстом на стороне бота (согласованно с vision §11–12). Реализация через middleware агента или постобработку — что ближе к текущей архитектуре (**YAGNI**). Флаг включения маски PAN в чат — **`MASK_PAN_OUTGOING`** (переменная окружения, описание в vision §9 и §12 и в **`.env.example`**).

**Проверка:** после успешного **`open_credit_card`** пользователь в чате не видит полный номер целиком (или видит по согласованному маскируемому формату из vision); логи приложения без полного PAN.

- [x] Слой маскирования + конфиг **`MASK_PAN_OUTGOING`** в **`.env.example`** и в **vision** / **`ReadMe`**

---

### Итерация 30 — Rate limiting и сборка

**Цель:** простой лимит частоты **текстовых** сообщений диалога на **`chat_id`** (скользящее окно); при превышении — короткий ответ без LLM. Глобальный флаг включения целиком — **`TELEGRAM_TEXT_RATE_LIMIT_ENABLED`** (вместе с окном **`TELEGRAM_TEXT_RATE_LIMIT_WINDOW_SECONDS`** и порогом **`TELEGRAM_TEXT_RATE_LIMIT_MAX_MESSAGES`**): документация в **`docs/vision.md`** (**§9**, **§12**) и **`ReadMe`** / **`.env.example`**. Файл **`make.sh`** в корне дублирует цели **`Makefile`** (**`run`**, **`run-mcp-bank`**, …), по смыслу как **`make.ps1`** (**vision §13**).

**Проверка:** при искусственном спаме срабатывает отказ; при **`TELEGRAM_TEXT_RATE_LIMIT_ENABLED=false`** текстовые сообщения всегда обрабатываются как раньше.

- [x] Реализация лимита и конфиг (**`TELEGRAM_TEXT_RATE_LIMIT_ENABLED`** и параметры порога)
- [x] **`make.sh`** и консистентность с **Makefile** / **`make.ps1`**

---

### Итерация 31 — Лимит обращений к агенту за интервал времени

**Контекст:** **итерация 30** ограничивает частоту **входящих текстовых сообщений** Telegram (хендлер **`plain_text`**) **до** вызова LLM. Иная задача — ограничить число **фактических обращений к графу агента** (один вызов **`BankAgentRunner.ainvoke_turn`** = один «ход» с возможным вызовом модели) на **`chat_id`** за скользящее окно времени. Например, один длинный текст пользователя даёт **одно** сообщение (ит. 30) и обычно **одно** обращение к агенту; сценарий HITL (**resume** после Accept/Reject) — **второе** обращение к агенту без нового текстового сообщения.

**Цель:** отдельный in-memory счётчик (по **`chat_id`**, скользящее окно) на число **`ainvoke_turn`** за интервал; в **`.env.example`**: **`AGENT_INVOCATIONS_RATE_LIMIT_ENABLED`**, **`WINDOW_AGENT_SECONDS`**, **`MAX_AGENT_INVOCATIONS_PER_WINDOW`** (в именах — подстрока **`AGENT`** для ясности); правки **vision.md** §9/§12 (отличие от **`TELEGRAM_TEXT_RATE_LIMIT_*`**); точки применения — пути, которые вызывают **`ainvoke_turn`** (как минимум **`plain_text`**, callback HITL **`hitl_callback`**); при превышении — короткий ответ **без** **`ainvoke_turn`**. Команды бота (**`/start`**, **`/index`**, …) — по согласованию с ит. 30 (обычно вне счётчика). **KISS**, без дублирования логики с ит. 30 где возможно.

**Проверка:** при превышении лимита «ходов» агента по **`chat_id`** — отказ без LLM; при нормальной нагрузке диалог и HITL не сломаны; переменные описаны в **vision** и **`.env.example`**.

- [x] Конфиг и модуль лимита (общая логика окна — **`sliding_window_chat_limiter`**)
- [x] Встраивание перед **`ainvoke_turn`** в **`plain_text`** и **`hitl_callback`**
- [x] **vision.md**, **`.env.example`**, **ReadMe**

---

### Итерация 32 — MCP `open_deposit`, HITL и промпт

**Цель:** в **`mcp/mcp-bank-agent`** добавить **`open_deposit(amount_rub, term_months, annual_rate_percent, application_note?)`** — мок открытия вклада с упрощённой оценкой **`estimated_interest_at_maturity_rub`** (простые проценты на срок); в агенте **`HumanInTheLoopMiddleware`** для **`open_deposit`** так же, как для **`open_credit_card`** (инструмент попадает в **`interrupt_on`** только если есть в **`get_tools()`**). В Telegram — те же inline **Accept** / **Reject**, **`Command(resume=…)`**, **`edit_reply_markup(None)`** после нажатия. В **`prompts/system.txt`** — правила, когда вызывать/не вызывать и примеры; выравнивание **vision.md** и **idea.md**.

**Проверка:** при запущенном MCP инструмент виден клиенту; сценарий «открыть вклад» останавливается на HITL с деталями в сообщении; Accept выполняет вызов MCP и даёт ответ; Reject отменяет без MCP; клавиатура снимается. Имя инструмента в MCP и в коде — **`open_deposit`** (одно подчёркивание).

- [x] **`mcp_bank_agent`**: **`deposit_mock.py`**, **`@mcp.tool` `open_deposit`** в **`server.py`**
- [x] **`bank_agent.py`**: **`interrupt_on`** для **`open_credit_card`** и **`open_deposit`**
- [x] **`hitl_callback`**, **`plain_text`**: общая клавиатура **`hitl_bank_operation_keyboard`**, callback **`hitl_bank_operation_callback`**
- [x] **`prompts/system.txt`**, **vision.md**, **idea.md**, **mcp-bank-agent/ReadMe.md**

**Статус закрытия итерации:** после вашей проверки в Telegram/MCP — подтвердите; затем в таблице прогресса можно выставить **Done**.

---

## Спринт 8 — E2E агента, agentevals (ДЗ10)

Цели — [vision.md](vision.md) §10 п. 5, §9, §13. Референс: **`data/agent-evaluation.ipynb`**. Принципы: **KISS**, без дублирования продукта в тестах — один **индекс**, **`BankAgentRunner`**, **`MCP_BANK_ENABLED=false`** в фикстуре.

### Прогресс

| № | Итерация | Статус |
|---|----------|--------|
| 33 | ДЗ10-1: документация (idea, vision, conventions, tasklist, .env.example) и сценарии e2e | 🚧 In Progress |
| 34 | ДЗ10-2: `tests/e2e`, dev-зависимости, Make / `make.ps1` / `make.sh`, `BankAgentRunner.aget_thread_messages` | 🚧 In Progress |

---

### Итерация 33 — ДЗ10-1: описание e2e и выбор сценариев

**Цель:** зафиксировать в **idea.md** / **vision.md** цель e2e по траектории; типы тестов — **детерминированное сопоставление** (**`create_async_trajectory_match_evaluator`**, режим **superset** + **ignore** аргументов) и **LLM-as-a-Judge** (**`create_async_trajectory_llm_as_judge`**, **`AGENTEVALS_LLM_MODEL`**); структура **`tests/e2e/`**; обновить **conventions.mdc** (ссылки на vision, без дублирения перечней); **`.env.example`**.

**Проверка:** в документах согласованы команды запуска и переменная судьи; референсная тетрадка указана.

- [ ] **idea.md**, **vision.md** (§2, §5, §9, §10 п. 5, §13, сводка)
- [ ] **conventions.mdc**
- [ ] **tasklist** (спринт ДЗ10)
- [ ] **`.env.example`**: **`AGENTEVALS_LLM_MODEL`**

**Статус:** черновик документации внесён в репозиторий; после вашей проверки — отметить чекбоксы и **Done** для ДЗ10-1.

---

### Итерация 34 — ДЗ10-2: реализация тестов и целей Make

**Цель:** три e2e-теста (два детерминированных на **`rag_search`** и **`convert_currency`**, один **LLM-judge**); зависимости **`dependency-groups.dev`** (**pytest**, **pytest-asyncio**, **agentevals**); цели **`test-e2e-agent`**, **`test-e2e-agent-deterministic`**, **`test-e2e-agent-judge`** в **Makefile** и дубли в **`make.ps1`** / **`make.sh`**; метод **`BankAgentRunner.aget_thread_messages`** для выдачи траектории.

**Проверка:** при заполненном **`.env`** (`make test-e2e-agent-deterministic`) проходят сопоставления; при **`AGENTEVALS_LLM_MODEL`** — прогон судьи; без ключа API — осмысленный **skip** / ошибка конфига, как у прочих smoke-команд.

- [ ] **`tests/__init__.py`**, **`tests/e2e/__init__.py`** (импорт **`tests.e2e.*`**)
- [ ] **`tests/e2e/conftest.py`**, детерминированные и judge-файлы
- [ ] **`pyproject.toml`**: группа **dev**, **`[tool.pytest.ini_options]`**
- [ ] **Makefile**, **`make.ps1`**, **`make.sh`**
- [ ] **`bank_agent.py`**: **`aget_thread_messages`**

**Статус:** реализация в репозитории согласована с текстом итераций; после вашей проверки прогонов **`make test-e2e-agent`** / чекбоксы — отметить выполненным и **Done** в таблице прогресса.
