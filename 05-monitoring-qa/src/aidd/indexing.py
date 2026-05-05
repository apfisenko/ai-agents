"""Загрузка документов из data/, сплит чанков и сборка InMemoryVectorStore."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Final

from langchain_community.document_loaders import PyPDFLoader
from langchain_core.documents import Document
from langchain_core.vectorstores import InMemoryVectorStore
from langchain_openai import OpenAIEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from openai import APIConnectionError

logger = logging.getLogger(__name__)

# Имена файлов — docs/vision.md §1
SOURCE_PDF_CREDIT: Final[str] = "ouk_potrebitelskiy_kredit_lph.pdf"
SOURCE_PDF_DEPOSITS: Final[str] = "usl_r_vkladov.pdf"
SOURCE_JSON_HELP: Final[str] = "sberbank_help_documents.json"

# Как в референсе data/naive-rag.ipynb
DEFAULT_CHUNK_SIZE: Final[int] = 1500
DEFAULT_CHUNK_OVERLAP: Final[int] = 150

DEFAULT_EMBEDDING_MODEL: Final[str] = "openai/text-embedding-3-small"


def default_data_dir() -> Path:
    """Каталог с источниками RAG: `DATA_DIR` / `RAG_DATA_DIR`, либо `data/` от cwd вверх по дереву."""
    raw = (os.environ.get("DATA_DIR") or os.environ.get("RAG_DATA_DIR") or "").strip()
    if raw:
        p = Path(raw).expanduser().resolve()
        if p.is_dir():
            return p
        raise ValueError(f"DATA_DIR / RAG_DATA_DIR не является каталогом: {p}")

    start = Path.cwd().resolve()
    for base in (start, *start.parents):
        candidate = base / "data"
        if candidate.is_dir():
            return candidate

    raise FileNotFoundError(
        "Не найден каталог data/ (обход от cwd вверх). "
        "Запускайте из корня репозитория или задайте DATA_DIR."
    )


def _load_pdf(path: Path) -> list[Document]:
    return PyPDFLoader(str(path)).load()


def _load_json_help(path: Path) -> list[Document]:
    """Одна запись массива с непустым `full_text` → один документ (без последующего чанкинга)."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError(f"Expected JSON array in {path}")
    docs: list[Document] = []
    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            continue
        text = (item.get("full_text") or "").strip()
        if not text:
            continue
        meta: dict[str, str | int] = {"source": path.name, "index": i}
        if u := item.get("url"):
            meta["url"] = str(u)
        if c := item.get("category"):
            meta["category"] = str(c)
        docs.append(Document(page_content=text, metadata=meta))
    return docs


def load_pdf_documents(data_dir: Path) -> list[Document]:
    """Только PDF из vision §1 — дальше проходят через RecursiveCharacterTextSplitter."""
    data_dir = data_dir.resolve()
    out: list[Document] = []

    pdf_credit = data_dir / SOURCE_PDF_CREDIT
    if pdf_credit.is_file():
        logger.info("Loading PDF %s", pdf_credit.name)
        out.extend(_load_pdf(pdf_credit))
    else:
        logger.warning("PDF not found (skipped): %s", pdf_credit)

    pdf_dep = data_dir / SOURCE_PDF_DEPOSITS
    if pdf_dep.is_file():
        logger.info("Loading PDF %s", pdf_dep.name)
        out.extend(_load_pdf(pdf_dep))
    else:
        logger.warning("PDF not found (skipped): %s", pdf_dep)

    return out


def load_json_documents(data_dir: Path) -> list[Document]:
    """JSON: каждая запись с полем `full_text` — отдельный документ (чанкинг не применяется)."""
    data_dir = data_dir.resolve()
    json_help = data_dir / SOURCE_JSON_HELP
    if json_help.is_file():
        logger.info("Loading JSON %s", json_help.name)
        return _load_json_help(json_help)
    logger.warning("JSON not found (skipped): %s", json_help)
    return []


def split_documents(
    documents: list[Document],
    *,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> list[Document]:
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\n\n\n", "\n\n", "\n", ". ", " ", ""],
        keep_separator=True,
    )
    return splitter.split_documents(documents)


def _env_float(name: str, default: float) -> float:
    raw = (os.environ.get(name) or "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _env_int(name: str, default: int, *, min_v: int, max_v: int) -> int:
    raw = (os.environ.get(name) or "").strip()
    if not raw:
        return default
    try:
        v = int(raw)
    except ValueError:
        return default
    return max(min_v, min(v, max_v))


def _embedding_http_proxy() -> str | None:
    """Явный proxy для httpx в OpenAIEmbeddings (HTTPS_PROXY часто нужен из-под Windows/VPN)."""
    for key in ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy"):
        v = (os.environ.get(key) or "").strip()
        if v:
            return v
    v = (os.environ.get("OPENAI_PROXY") or "").strip()
    return v or None


def make_embeddings(
    *,
    open_api_key: str,
    open_base_url: str,
    embedding_model: str,
) -> OpenAIEmbeddings:
    # OpenRouter: без tiktoken по имени модели; устойчивость сети — таймаут, меньшие батчи, ретраи.
    timeout = _env_float("EMBEDDING_REQUEST_TIMEOUT", 180.0)
    batch = _env_int("EMBEDDING_BATCH_SIZE", 64, min_v=1, max_v=512)
    retries = _env_int("EMBEDDING_MAX_RETRIES", 5, min_v=0, max_v=12)
    proxy = _embedding_http_proxy()
    kwargs: dict = {
        "model": embedding_model,
        "api_key": open_api_key,
        "base_url": open_base_url,
        "check_embedding_ctx_length": False,
        "tiktoken_enabled": False,
        "request_timeout": timeout,
        "chunk_size": batch,
        "max_retries": retries,
    }
    if proxy:
        kwargs["openai_proxy"] = proxy
    return OpenAIEmbeddings(**kwargs)


def build_vector_store(
    *,
    data_dir: Path,
    open_api_key: str,
    open_base_url: str,
    embedding_model: str = DEFAULT_EMBEDDING_MODEL,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> tuple[InMemoryVectorStore, int]:
    """
    Полный пайплайн: PDF → сплит чанков; JSON (`full_text`) → по одному документу на запись;
    затем эмбеддинги → InMemoryVectorStore.

    Returns:
        (store, num_chunks)
    """
    base_url = open_base_url.rstrip("/")
    pdf_docs = load_pdf_documents(data_dir)
    json_docs = load_json_documents(data_dir)
    if not pdf_docs and not json_docs:
        raise ValueError(
            f"No documents loaded from {data_dir}. "
            f"Add at least {SOURCE_JSON_HELP} (записи с full_text) or PDFs from vision §1."
        )
    split_pdf = split_documents(pdf_docs, chunk_size=chunk_size, chunk_overlap=chunk_overlap) if pdf_docs else []
    splits = split_pdf + json_docs
    logger.info("Модель эмбеддингов: %s", embedding_model)
    embeddings = make_embeddings(
        open_api_key=open_api_key,
        open_base_url=base_url,
        embedding_model=embedding_model,
    )
    try:
        store = InMemoryVectorStore.from_documents(splits, embeddings)
    except APIConnectionError as e:
        hint = (
            "Проверьте доступ к интернету и до OPEN_BASE_URL (эмбеддинги запрашиваются "
            "на том же базовом URL, что и chat API). За прокси/VPN задайте HTTPS_PROXY или "
            "HTTP_PROXY со схемой, например http://127.0.0.1:11301. При медленной сети "
            "увеличьте EMBEDDING_REQUEST_TIMEOUT (сек.) или уменьшите EMBEDDING_BATCH_SIZE. "
            "См. .env.example и ReadMe."
        )
        raise RuntimeError(f"Ошибка подключения к API эмбеддингов при индексации. {hint}") from e
    return store, len(splits)
