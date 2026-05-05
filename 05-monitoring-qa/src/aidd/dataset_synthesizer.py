"""Синтез Q&A-датасета по vision §10 и выгрузка в LangSmith (make dataset / dataset-upload)."""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
from pathlib import Path
from typing import Any, Final

import dotenv
from datasets import Dataset
from langchain_community.document_loaders import PyPDFLoader
from langchain_core.documents import Document
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langsmith import Client

from aidd.indexing import (
    SOURCE_JSON_HELP,
    SOURCE_PDF_CREDIT,
    SOURCE_PDF_DEPOSITS,
    DEFAULT_CHUNK_OVERLAP,
    DEFAULT_CHUNK_SIZE,
    default_data_dir,
    split_documents,
)

logger = logging.getLogger(__name__)

DATASET_FILENAME: Final[str] = "05-rag-qa-dataset.json"
SYNTHESIS_SYSTEM: Final[str] = (
    "Ты эксперт по созданию вопросно-ответных пар для оценки RAG.\n"
    "На основе текста создай ровно {num_questions} вопрос(а/ов) и короткий точный ответ "
    "только по этому тексту.\n"
    "Вопрос — как у реального пользователя, ответ — фактологически верный тексту.\n\n"
    "Верни ТОЛЬКО валидный JSON без текста до или после:\n"
    '{{"qa_pairs": [{{"question": "...", "answer": "..."}}]}}\n'
)
MAX_CHUNK_TEXT: Final[int] = 2000
CHUNKS_PER_PDF: Final[int] = 2


def repo_root_containing_dataset_dir(start: Path) -> Path:
    for base in (start, *start.parents):
        if (base / "datasets").is_dir() or (base / "data").is_dir():
            return base
    return start


def output_json_path(repo: Path | None = None) -> Path:
    root = repo or repo_root_containing_dataset_dir(Path.cwd().resolve())
    return (root / "datasets" / DATASET_FILENAME).resolve()


def _norm_question(q: str) -> str:
    return re.sub(r"\s+", " ", (q or "").strip().lower())


def _extract_json_obj(raw: str) -> str:
    content = raw.strip()
    if "```json" in content:
        content = content.split("```json", 1)[1].split("```", 1)[0].strip()
    elif "```" in content:
        parts = content.split("```")
        if len(parts) >= 2:
            inner = parts[1].strip()
            if inner.startswith("json"):
                inner = inner[4:].strip()
            content = inner
    content = content.strip()
    if not content.startswith("{"):
        idx = content.find("{")
        if idx >= 0:
            content = content[idx:]
    return content


def load_pdf_chunks(
    pdf_path: Path,
    *,
    chunk_size: int,
    chunk_overlap: int,
) -> list[Document]:
    if not pdf_path.is_file():
        logger.warning("PDF не найден, пропуск: %s", pdf_path.name)
        return []
    docs = PyPDFLoader(str(pdf_path)).load()
    return split_documents(
        docs, chunk_size=chunk_size, chunk_overlap=chunk_overlap
    )


def pick_chunks_for_synthesis(chunks: list[Document]) -> list[Document]:
    if not chunks:
        return []
    n = len(chunks)
    if n <= CHUNKS_PER_PDF:
        return list(chunks)
    second_idx = max(1, n // 2)
    pair = [chunks[0], chunks[second_idx]]
    if pair[0].page_content == pair[1].page_content and n > second_idx + 1:
        pair[1] = chunks[-1]
    return pair


def synthesize_one_pair(
    llm: ChatOpenAI,
    chunk: Document,
    *,
    questions_per_chunk: int = 1,
) -> list[dict[str, Any]]:
    text = chunk.page_content.strip()
    if len(text) < 80:
        logger.info("Чанк слишком короткий для синтеза (<80 симв.), пропуск")
        return []
    clipped = text[:MAX_CHUNK_TEXT]
    messages = [
        SystemMessage(
            content=SYNTHESIS_SYSTEM.format(num_questions=questions_per_chunk)
        ),
        HumanMessage(content=f"Текст:\n{clipped}"),
    ]
    resp = llm.invoke(messages)
    content = getattr(resp, "content", "")
    if isinstance(content, str):
        raw = content.strip()
    elif isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict):
                t = block.get("text")
                if isinstance(t, str):
                    parts.append(t)
            elif isinstance(block, str):
                parts.append(block)
        raw = "".join(parts).strip()
    else:
        raw = str(content or "").strip()
    try:
        data = json.loads(_extract_json_obj(raw))
    except json.JSONDecodeError as e:
        logger.warning(
            "Не удалось разобрать JSON ответа LLM для чанка (%s…): %s",
            clipped[:40],
            e,
        )
        return []

    meta_base = chunk.metadata or {}
    source = meta_base.get("source", "unknown")
    page = meta_base.get("page")
    out: list[dict[str, Any]] = []
    for qa in data.get("qa_pairs", []):
        q = (qa.get("question") or "").strip()
        a = (qa.get("answer") or "").strip()
        if not q or not a:
            continue
        row: dict[str, Any] = {
            "question": q,
            "ground_truth": a,
            "contexts": [text],
            "metadata": {
                "source": str(source),
                "origin": "synthetic_pdf",
            },
        }
        if isinstance(page, int):
            row["metadata"]["page"] = page
        out.append(row)
    return out


def load_json_qa_rows(data_dir: Path) -> list[dict[str, Any]]:
    path = data_dir / SOURCE_JSON_HELP
    if not path.is_file():
        logger.warning("JSON со справкой не найден: %s", path.name)
        return []
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        return []
    rows: list[dict[str, Any]] = []
    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            continue
        q = (item.get("question") or "").strip()
        a = (item.get("answer") or "").strip()
        ft = (item.get("full_text") or "").strip()
        if not q or not a:
            continue
        ctx = ft if ft else f"{q}\n{a}"
        rows.append(
            {
                "question": q,
                "ground_truth": a,
                "contexts": [ctx],
                "metadata": {
                    "source": path.name,
                    "index": i,
                    "origin": "json_help",
                },
            }
        )
    logger.info("Загружено Q&A из JSON: %s записей", len(rows))
    return rows


def merge_unique_rows(
    *row_groups: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    seen: set[str] = set()
    merged: list[dict[str, Any]] = []
    for group in row_groups:
        for row in group:
            key = _norm_question(row["question"])
            if not key or key in seen:
                continue
            seen.add(key)
            merged.append(row)
    return merged


def save_dataset_json(path: Path, records: list[dict[str, Any]]) -> None:
    Dataset.from_list(records)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)
    logger.info("Сохранено %s записей в %s", len(records), path)


def synthesize_pdf_portion(
    data_dir: Path,
    *,
    chunk_size: int,
    chunk_overlap: int,
    llm: ChatOpenAI,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for fname in (SOURCE_PDF_CREDIT, SOURCE_PDF_DEPOSITS):
        path = data_dir / fname
        chunks = load_pdf_chunks(
            path,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )
        picks = pick_chunks_for_synthesis(chunks)
        logger.info("%s: чанков всего=%s, к синтезу=%s", fname, len(chunks), len(picks))
        for ch in picks:
            rows.extend(synthesize_one_pair(llm, ch))
    return rows


def build_full_dataset(
    *,
    data_dir: Path,
    open_api_key: str,
    open_base_url: str,
    llm_model: str,
    max_tokens: int,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> list[dict[str, Any]]:
    llm = ChatOpenAI(
        model=llm_model,
        api_key=open_api_key,
        base_url=open_base_url.rstrip("/"),
        temperature=0.7,
        max_tokens=max_tokens,
    )
    synth = synthesize_pdf_portion(
        data_dir,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        llm=llm,
    )
    json_rows = load_json_qa_rows(data_dir)
    return merge_unique_rows(json_rows, synth)


def records_to_langsmith_examples(
    records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    examples: list[dict[str, Any]] = []
    for row in records:
        meta = dict(row.get("metadata") or {})
        meta["contexts"] = row.get("contexts") or []
        examples.append(
            {
                "inputs": {"question": row["question"]},
                "outputs": {"answer": row["ground_truth"]},
                "metadata": meta,
            }
        )
    return examples


def existing_questions_norm(client: Client, dataset_name: str) -> set[str]:
    ds_list = list(client.list_datasets(dataset_name=dataset_name))
    if not ds_list:
        return set()
    ds_id = ds_list[0].id
    seen: set[str] = set()
    for ex in client.list_examples(dataset_id=ds_id):
        q = (ex.inputs or {}).get("question") or ""
        nq = _norm_question(str(q))
        if nq:
            seen.add(nq)
    return seen


def upload_dataset_langsmith(
    records: list[dict[str, Any]],
    *,
    dataset_name: str,
    description: str,
) -> tuple[int, int]:
    client = Client()
    existing = list(client.list_datasets(dataset_name=dataset_name))
    if existing:
        ds = existing[0]
        logger.info("Датасет LangSmith уже есть: %s (%s)", dataset_name, ds.id)
    else:
        ds = client.create_dataset(
            dataset_name=dataset_name,
            description=description,
        )
        logger.info("Создан датасет LangSmith: %s (%s)", dataset_name, ds.id)

    already = existing_questions_norm(client, dataset_name)
    examples = records_to_langsmith_examples(records)
    new_ex: list[dict[str, Any]] = []
    for ex in examples:
        qn = _norm_question(str(ex["inputs"]["question"]))
        if qn in already:
            continue
        already.add(qn)
        new_ex.append(ex)

    if not new_ex:
        logger.info("Новых примеров для загрузки нет (все дубликаты).")
        return len(examples), 0

    client.create_examples(dataset_id=ds.id, examples=new_ex)
    logger.info("Загружено новых примеров: %s (всего в файле: %s)", len(new_ex), len(examples))
    return len(examples), len(new_ex)


def cmd_synthesize(args: argparse.Namespace) -> int:
    data_dir = Path(args.data_dir).expanduser().resolve() if args.data_dir else default_data_dir()
    out = Path(args.output).expanduser().resolve() if args.output else output_json_path()

    key = (os.environ.get("OPEN_API_KEY") or "").strip()
    base = (os.environ.get("OPEN_BASE_URL") or "").strip().rstrip("/")
    model = (os.environ.get("LLM_MODEL") or "").strip()
    raw_max = (os.environ.get("LLM_MAX_COMPLETION_TOKENS") or "1024").strip()

    if not key or not base or not model:
        print(
            "Нужны OPEN_API_KEY, OPEN_BASE_URL, LLM_MODEL (см. .env.example).",
            file=sys.stderr,
        )
        return 1
    try:
        max_tok = max(256, min(4096, int(raw_max)))
    except ValueError:
        max_tok = 1024

    records = build_full_dataset(
        data_dir=data_dir,
        open_api_key=key,
        open_base_url=base,
        llm_model=model,
        max_tokens=max_tok,
    )
    if not records:
        print("Пустой датасет: нет PDF-чанков и Q&A из JSON.", file=sys.stderr)
        return 1

    save_dataset_json(out, records)
    return 0


def cmd_upload(args: argparse.Namespace) -> int:
    path = Path(args.input).expanduser().resolve() if args.input else output_json_path()
    if not path.is_file():
        print(f"Файл датасета не найден: {path}", file=sys.stderr)
        return 1

    name = (os.environ.get("LANGSMITH_DATASET_NAME") or "").strip() or "05-rag-qa-dataset"
    desc = (os.environ.get("LANGSMITH_DATASET_DESCRIPTION") or "").strip() or (
        "Q&A для оценки RAG (синтез по PDF + JSON), проект aidd"
    )

    key = (os.environ.get("LANGSMITH_API_KEY") or os.environ.get("LANGCHAIN_API_KEY") or "").strip()
    if not key:
        print(
            "Для выгрузки нужен LANGSMITH_API_KEY (или LANGCHAIN_API_KEY).",
            file=sys.stderr,
        )
        return 1

    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        print("Ожидался JSON-массив записей.", file=sys.stderr)
        return 1

    total, uploaded = upload_dataset_langsmith(
        raw,
        dataset_name=name,
        description=desc,
    )
    print(f"Записей в файле: {total}; загружено новых: {uploaded}")
    return 0


def main(argv: list[str] | None = None) -> int:
    dotenv.load_dotenv(Path.cwd() / ".env", override=False)
    logging.basicConfig(
        level=(os.environ.get("LOG_LEVEL") or "INFO").strip().upper(),
        format="%(levelname)s %(name)s: %(message)s",
    )

    parser = argparse.ArgumentParser(
        description="Синтез datasets/05-rag-qa-dataset.json и выгрузка в LangSmith."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_syn = sub.add_parser("synthesize", help="Собрать JSON (PDF + LLM + merge JSON)")
    p_syn.add_argument(
        "--data-dir",
        type=str,
        default=None,
        help="Каталог с data/ (по умолчанию — как в indexing.default_data_dir)",
    )
    p_syn.add_argument(
        "--output",
        "-o",
        type=str,
        default=None,
        help=f"Путь к JSON (по умолчанию datasets/{DATASET_FILENAME})",
    )
    p_syn.set_defaults(func=cmd_synthesize)

    p_up = sub.add_parser("upload", help="Загрузить JSON в LangSmith без дубликатов по вопросу")
    p_up.add_argument(
        "--input",
        "-i",
        type=str,
        default=None,
        help=f"Путь к JSON (по умолчанию datasets/{DATASET_FILENAME})",
    )
    p_up.set_defaults(func=cmd_upload)

    ns = parser.parse_args(argv)
    return int(ns.func(ns))


if __name__ == "__main__":
    raise SystemExit(main())
