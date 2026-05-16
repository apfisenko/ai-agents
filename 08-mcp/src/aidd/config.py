from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal, Tuple

from aidd.indexing import DEFAULT_EMBEDDING_MODEL, DEFAULT_HF_EMBEDDING_MODEL

logger = logging.getLogger(__name__)

REQUIRED: Final[Tuple[str, ...]] = (
    "TELEGRAM_BOT_TOKEN",
    "OPEN_API_KEY",
    "LLM_MODEL",
    "OPEN_BASE_URL",
    "SYSTEM_PROMPT_PATH",
    "LLM_MAX_COMPLETION_TOKENS",
    "RETRIEVER_K",
)

RagRetrievalMode = Literal["semantic", "hybrid", "hybrid_rerank"]
EmbeddingProvider = Literal["openai", "huggingface"]


def _parse_llm_max_completion_tokens(raw: str) -> int:
    s = raw.strip()
    try:
        v = int(s)
    except ValueError:
        raise ValueError(
            f"LLM_MAX_COMPLETION_TOKENS must be an integer between 64 and 8192, got: {raw!r}"
        ) from None
    if v < 64 or v > 8192:
        raise ValueError(
            "LLM_MAX_COMPLETION_TOKENS must be an integer between 64 and 8192 "
            f"(got {v})"
        )
    return v


def _parse_retriever_k(raw: str) -> int:
    s = raw.strip()
    try:
        v = int(s)
    except ValueError:
        raise ValueError(
            f"RETRIEVER_K must be an integer between 1 and 50, got: {raw!r}"
        ) from None
    if v < 1 or v > 50:
        raise ValueError(f"RETRIEVER_K must be between 1 and 50 (got {v})")
    return v


def _parse_bounded_int(
    raw: str,
    name: str,
    lo: int,
    hi: int,
) -> int:
    s = raw.strip()
    try:
        v = int(s)
    except ValueError:
        raise ValueError(
            f"{name} must be an integer between {lo} and {hi}, got: {raw!r}"
        ) from None
    if v < lo or v > hi:
        raise ValueError(f"{name} must be between {lo} and {hi} (got {v})")
    return v


def _parse_show_sources(raw: str | None) -> bool:
    s = (raw or "").strip().lower()
    return s in ("true", "1", "yes")


def _parse_mcp_bank_enabled(raw: str | None) -> bool:
    """По умолчанию True — пытаемся подключиться к MCP (graceful degradation при ошибке)."""
    s = (raw or "").strip().lower()
    if not s:
        return True
    if s in ("0", "false", "no", "off"):
        return False
    if s in ("1", "true", "yes", "on"):
        return True
    return True


def _parse_rag_retrieval_mode(raw: str | None) -> RagRetrievalMode:
    s = (raw or "").strip().lower()
    if not s:
        return "semantic"
    if s in ("semantic", "hybrid", "hybrid_rerank"):
        return s  # type: ignore[return-value]
    raise ValueError(
        "RAG_RETRIEVAL_MODE must be one of: semantic, hybrid, hybrid_rerank "
        f"(got {raw!r})"
    )


def _parse_embedding_provider(raw: str | None) -> EmbeddingProvider:
    s = (raw or "").strip().lower()
    if not s:
        return "openai"
    if s in ("openai", "huggingface"):
        return s  # type: ignore[return-value]
    raise ValueError(
        "EMBEDDING_PROVIDER must be one of: openai, huggingface "
        f"(got {raw!r})"
    )


def _parse_ragas_embedding_provider(
    raw: str | None, fallback: EmbeddingProvider
) -> EmbeddingProvider:
    s = (raw or "").strip().lower()
    if not s:
        return fallback
    if s in ("openai", "huggingface"):
        return s  # type: ignore[return-value]
    raise ValueError(
        "RAGAS_EMBEDDING_PROVIDER must be one of: openai, huggingface "
        f"(got {raw!r})"
    )


def _parse_optional_float(raw: str | None, default: float) -> float:
    if raw is None or not str(raw).strip():
        return default
    try:
        return float(str(raw).strip())
    except ValueError:
        raise ValueError(f"expected a float, got: {raw!r}") from None


def _validate_hybrid_weights(sem: float, bm25: float) -> None:
    s = sem + bm25
    if s <= 0:
        raise ValueError(
            "HYBRID_SEMANTIC_WEIGHT + HYBRID_BM25_WEIGHT must be positive "
            f"(got {sem!r} + {bm25!r})"
        )
    if abs(s - 1.0) > 1e-3:
        raise ValueError(
            "HYBRID_SEMANTIC_WEIGHT and HYBRID_BM25_WEIGHT must sum to 1.0 "
            f"(got sum {s:.6f})"
        )


def _looks_like_openai_embedding_api_id(model: str) -> bool:
    """Имена вида openai/text-embedding-* / text-embedding-3-* — для API, не HF Hub + sentence-transformers."""
    m = model.strip().lower()
    if m.startswith("openai/text-embedding"):
        return True
    if m.startswith("text-embedding-3"):
        return True
    return False


def _validate_embedding_model_for_provider(
    provider: EmbeddingProvider, model: str, *, var_name: str = "EMBEDDING_MODEL"
) -> None:
    if provider != "huggingface":
        return
    if _looks_like_openai_embedding_api_id(model):
        raise ValueError(
            f"{var_name}={model!r}: при провайдере huggingface укажите id модели с Hugging Face "
            "(например intfloat/multilingual-e5-base). Суффикс openai/text-embedding-* относится к API "
            "OpenAI/OpenRouter — для него задайте EMBEDDING_PROVIDER=openai."
        )


@dataclass(frozen=True)
class AppConfig:
    telegram_bot_token: str
    open_api_key: str
    llm_model: str
    llm_query_transform_model: str
    open_base_url: str
    system_prompt_path: Path
    system_prompt_text: str
    log_level: str
    llm_max_completion_tokens: int
    retriever_k: int
    semantic_k: int
    rag_retrieval_mode: RagRetrievalMode
    embedding_provider: EmbeddingProvider
    embedding_model: str
    bm25_k: int
    hybrid_semantic_weight: float
    hybrid_bm25_weight: float
    cross_encoder_model: str
    rerank_candidate_pool: int
    rerank_top_k: int
    ragas_llm_model: str
    ragas_llm_max_completion_tokens: int
    ragas_embedding_provider: EmbeddingProvider
    ragas_embedding_model: str
    show_sources: bool
    mcp_bank_enabled: bool
    mcp_bank_streamable_http_url: str

    @staticmethod
    def from_env() -> "AppConfig":
        missing = [k for k in REQUIRED if not (os.environ.get(k) or "").strip()]
        if missing:
            raise ValueError(
                f"Missing or empty required environment variable(s): {', '.join(missing)}"
            )
        sp = Path(os.environ["SYSTEM_PROMPT_PATH"].strip()).expanduser()
        if not sp.is_file():
            raise ValueError(
                f"SYSTEM_PROMPT_PATH is not a path to a readable file: {sp} "
                f"(set an existing file; see .env.example)"
            )
        try:
            raw = sp.read_text(encoding="utf-8")
        except OSError as e:
            raise ValueError(f"Cannot read SYSTEM_PROMPT_PATH file: {sp}") from e
        if raw.startswith("\ufeff"):
            raw = raw[1:]
        system_prompt_text = raw.strip()
        log_level = (os.environ.get("LOG_LEVEL") or "INFO").strip().upper()
        llm_max = _parse_llm_max_completion_tokens(
            os.environ["LLM_MAX_COMPLETION_TOKENS"]
        )
        retriever_k = _parse_retriever_k(os.environ["RETRIEVER_K"])
        sem_raw = (os.environ.get("SEMANTIC_K") or "").strip()
        semantic_k = (
            _parse_bounded_int(sem_raw, "SEMANTIC_K", 1, 50)
            if sem_raw
            else retriever_k
        )

        rag_mode = _parse_rag_retrieval_mode(os.environ.get("RAG_RETRIEVAL_MODE"))
        embedding_provider = _parse_embedding_provider(
            os.environ.get("EMBEDDING_PROVIDER")
        )

        embedding_raw = (os.environ.get("EMBEDDING_MODEL") or "").strip()
        if embedding_provider == "huggingface":
            embedding_model = embedding_raw or DEFAULT_HF_EMBEDDING_MODEL
        else:
            embedding_model = embedding_raw or DEFAULT_EMBEDDING_MODEL
        _validate_embedding_model_for_provider(embedding_provider, embedding_model)

        bm25_raw = (os.environ.get("BM25_K") or "").strip()
        bm25_k = (
            _parse_bounded_int(bm25_raw, "BM25_K", 1, 50)
            if bm25_raw
            else 5
        )

        hybrid_sem = _parse_optional_float(
            os.environ.get("HYBRID_SEMANTIC_WEIGHT"), 0.5
        )
        hybrid_bm25_w = _parse_optional_float(
            os.environ.get("HYBRID_BM25_WEIGHT"), 0.5
        )
        if rag_mode in ("hybrid", "hybrid_rerank"):
            _validate_hybrid_weights(hybrid_sem, hybrid_bm25_w)

        cross_encoder_model = (os.environ.get("CROSS_ENCODER_MODEL") or "").strip()
        r_pool_raw = (os.environ.get("RERANK_CANDIDATE_POOL") or "").strip()
        rerank_candidate_pool = (
            _parse_bounded_int(r_pool_raw, "RERANK_CANDIDATE_POOL", 2, 200)
            if r_pool_raw
            else 20
        )
        r_top_raw = (os.environ.get("RERANK_TOP_K") or "").strip()
        rerank_top_k = (
            _parse_bounded_int(r_top_raw, "RERANK_TOP_K", 1, 50)
            if r_top_raw
            else 5
        )

        if rag_mode == "hybrid_rerank":
            if not cross_encoder_model:
                raise ValueError(
                    "CROSS_ENCODER_MODEL is required when RAG_RETRIEVAL_MODE=hybrid_rerank "
                    "(sentence-transformers CrossEncoder model id)"
                )
            if rerank_candidate_pool < max(semantic_k, bm25_k):
                logger.warning(
                    "RERANK_CANDIDATE_POOL (%s) is less than max(SEMANTIC_K, BM25_K); "
                    "pool may be too small for hybrid rerank",
                    rerank_candidate_pool,
                )
            if rerank_top_k > rerank_candidate_pool:
                raise ValueError(
                    "RERANK_TOP_K must be <= RERANK_CANDIDATE_POOL "
                    f"(got {rerank_top_k} > {rerank_candidate_pool})"
                )

        llm_model = os.environ["LLM_MODEL"].strip()
        qt_raw = (os.environ.get("LLM_QUERY_TRANSFORM_MODEL") or "").strip()
        llm_query_transform_model = qt_raw or llm_model
        show_sources = _parse_show_sources(os.environ.get("SHOW_SOURCES"))

        ragas_llm = (os.environ.get("RAGAS_LLM_MODEL") or "").strip() or llm_model
        ragas_max_raw = (os.environ.get("RAGAS_LLM_MAX_COMPLETION_TOKENS") or "").strip()
        ragas_llm_max_completion_tokens = (
            _parse_llm_max_completion_tokens(ragas_max_raw)
            if ragas_max_raw
            else llm_max
        )
        ragas_emb_prov = _parse_ragas_embedding_provider(
            os.environ.get("RAGAS_EMBEDDING_PROVIDER"), embedding_provider
        )
        ragas_emb_raw = (os.environ.get("RAGAS_EMBEDDING_MODEL") or "").strip()
        if ragas_emb_raw:
            ragas_emb_model = ragas_emb_raw
        elif ragas_emb_prov == "huggingface":
            ragas_emb_model = (
                embedding_model
                if embedding_provider == "huggingface"
                else DEFAULT_HF_EMBEDDING_MODEL
            )
        else:
            ragas_emb_model = embedding_model
        _validate_embedding_model_for_provider(
            ragas_emb_prov, ragas_emb_model, var_name="RAGAS_EMBEDDING_MODEL"
        )

        mcp_bank_enabled = _parse_mcp_bank_enabled(os.environ.get("MCP_BANK_ENABLED"))
        mcp_url = (os.environ.get("MCP_BANK_STREAMABLE_HTTP_URL") or "").strip()
        mcp_bank_streamable_http_url = mcp_url or "http://127.0.0.1:8000/mcp"

        return AppConfig(
            telegram_bot_token=os.environ["TELEGRAM_BOT_TOKEN"].strip(),
            open_api_key=os.environ["OPEN_API_KEY"].strip(),
            llm_model=llm_model,
            llm_query_transform_model=llm_query_transform_model,
            open_base_url=os.environ["OPEN_BASE_URL"].strip().rstrip("/"),
            system_prompt_path=sp.resolve(),
            system_prompt_text=system_prompt_text,
            log_level=log_level,
            llm_max_completion_tokens=llm_max,
            retriever_k=retriever_k,
            semantic_k=semantic_k,
            rag_retrieval_mode=rag_mode,
            embedding_provider=embedding_provider,
            embedding_model=embedding_model,
            bm25_k=bm25_k,
            hybrid_semantic_weight=hybrid_sem,
            hybrid_bm25_weight=hybrid_bm25_w,
            cross_encoder_model=cross_encoder_model,
            rerank_candidate_pool=rerank_candidate_pool,
            rerank_top_k=rerank_top_k,
            ragas_llm_model=ragas_llm,
            ragas_llm_max_completion_tokens=ragas_llm_max_completion_tokens,
            ragas_embedding_provider=ragas_emb_prov,
            ragas_embedding_model=ragas_emb_model,
            show_sources=show_sources,
            mcp_bank_enabled=mcp_bank_enabled,
            mcp_bank_streamable_http_url=mcp_bank_streamable_http_url,
        )
