"""Оценка RAG по датасету: LangSmith experiment + RAGAS + feedback (vision §10 п.4)."""

from __future__ import annotations

import asyncio
import logging
import math
import os
from dataclasses import dataclass
from typing import Any, Final, Iterator

from datasets import Dataset as HFDataset
from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI
from langsmith import Client

from ragas import evaluate as ragas_evaluate
from ragas.embeddings import LangchainEmbeddingsWrapper
from ragas.llms import LangchainLLMWrapper
from ragas.metrics import (
    AnswerCorrectness,
    AnswerRelevancy,
    AnswerSimilarity,
    ContextPrecision,
    ContextRecall,
    Faithfulness,
)
from ragas.run_config import RunConfig

from aidd.indexing import DEFAULT_EMBEDDING_MODEL, make_embeddings
from aidd.rag_chain import RagChainRunner

logger = logging.getLogger(__name__)


def _run_coro_sync(coro):
    """Выполнить корутину в новом цикле (обход asyncio.run после nest_asyncio и прочих патчей)."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        try:
            pending = [t for t in asyncio.all_tasks(loop) if not t.done()]
            for task in pending:
                task.cancel()
            if pending:
                loop.run_until_complete(
                    asyncio.gather(*pending, return_exceptions=True)
                )
        except Exception:
            pass
        loop.close()
        asyncio.set_event_loop(None)


METRIC_NAMES: Final[tuple[str, ...]] = (
    "faithfulness",
    "answer_relevancy",
    "answer_correctness",
    "answer_similarity",
    "context_recall",
    "context_precision",
)


class EvaluationError(Exception):
    """Ошибка конфигурации или прогона оценки (сообщение можно показать в Telegram)."""


@dataclass(frozen=True)
class EvaluationRunSummary:
    num_examples: int
    means: dict[str, float | None]
    experiment_name: str
    comparison_url: str | None
    feedback_rows: int


def _parse_eval_limit() -> int | None:
    raw = (os.environ.get("EVAL_MAX_EXAMPLES") or "").strip()
    if not raw:
        return 30
    if raw.lower() in ("0", "none", "all"):
        return None
    try:
        v = int(raw)
    except ValueError:
        return 30
    return max(1, min(v, 500))


def _safe_float(val: Any) -> float | None:
    if val is None:
        return None
    try:
        x = float(val)
    except (TypeError, ValueError):
        return None
    if isinstance(x, float) and math.isnan(x):
        return None
    return x


def _langsmith_api_key() -> str:
    return (os.environ.get("LANGSMITH_API_KEY") or os.environ.get("LANGCHAIN_API_KEY") or "").strip()


def _dataset_name() -> str:
    return (
        (os.environ.get("LANGSMITH_DATASET_NAME") or "").strip()
        or "05-rag-qa-dataset"
    )


def _parse_ragas_show_progress() -> bool:
    """Полоса RAGAS в IDE/логах часто не обновляется; tqdm только по явному env."""
    raw = (os.environ.get("RAGAS_SHOW_PROGRESS") or "").strip().lower()
    return raw in ("1", "true", "yes", "on")


def _parse_ragas_max_workers() -> int:
    raw = (os.environ.get("RAGAS_MAX_WORKERS") or "").strip()
    if not raw:
        return 1
    try:
        v = int(raw)
    except ValueError:
        return 1
    return max(1, min(v, 16))


def _examples_for_eval(client: Client, dataset_name: str, limit: int | None) -> Iterator[Any]:
    for i, ex in enumerate(client.list_examples(dataset_name=dataset_name)):
        if limit is not None and i >= limit:
            break
        yield ex


def _make_rag_target(rag_runner: RagChainRunner):
    def target(inputs: dict[str, Any], **_: Any) -> dict[str, Any]:
        q = str(inputs.get("question") or "").strip()
        if not q:
            return {"answer": "", "documents": []}

        async def _arun() -> dict[str, Any]:
            res = await rag_runner.ainvoke([HumanMessage(content=q)])
            docs: list[dict[str, Any]] = []
            for d in res.documents:
                docs.append(
                    {
                        "page_content": d.page_content,
                        "metadata": dict(d.metadata or {}),
                    }
                )
            return {"answer": res.text, "documents": docs}

        return _run_coro_sync(_arun())

    return target


def _documents_to_contexts(documents: Any) -> list[str]:
    if not documents:
        return []
    out: list[str] = []
    for item in documents:
        if isinstance(item, dict):
            pc = item.get("page_content")
            if isinstance(pc, str) and pc.strip():
                out.append(pc)
            continue
        pc = getattr(item, "page_content", None)
        if isinstance(pc, str) and pc.strip():
            out.append(pc)
    return out


def _build_ragas_metrics(
    ragas_llm: LangchainLLMWrapper,
    ragas_embeddings: LangchainEmbeddingsWrapper,
) -> list[Any]:
    answer_similarity_metric = AnswerSimilarity(embeddings=ragas_embeddings)
    return [
        Faithfulness(llm=ragas_llm),
        AnswerRelevancy(
            llm=ragas_llm,
            embeddings=ragas_embeddings,
            strictness=1,
        ),
        AnswerCorrectness(
            llm=ragas_llm,
            embeddings=ragas_embeddings,
            answer_similarity=answer_similarity_metric,
        ),
        answer_similarity_metric,
        ContextRecall(llm=ragas_llm),
        ContextPrecision(llm=ragas_llm),
    ]


def run_ragas_evaluation_with_feedback(rag_runner: RagChainRunner) -> EvaluationRunSummary:
    """Синхронный прогон: worker-thread (RAG через отдельный event loop — см. `_run_coro_sync`)."""
    ls_key = _langsmith_api_key()
    if not ls_key:
        raise EvaluationError(
            "Не задан LANGSMITH_API_KEY (или LANGCHAIN_API_KEY). Нужен для эксперимента и feedback."
        )

    cfg = rag_runner.app_config
    base = cfg.open_base_url.rstrip("/")
    router_key = cfg.open_api_key
    ragas_llm_id = (os.environ.get("RAGAS_LLM_MODEL") or cfg.llm_model).strip()
    emb_raw = (
        os.environ.get("RAGAS_EMBEDDING_MODEL") or cfg.embedding_model or DEFAULT_EMBEDDING_MODEL
    ).strip()

    lc_llm = ChatOpenAI(
        model=ragas_llm_id,
        api_key=router_key,
        base_url=base,
        temperature=0.0,
        max_tokens=2048,
    )
    lc_embeddings = make_embeddings(
        open_api_key=router_key,
        open_base_url=base,
        embedding_model=emb_raw,
    )
    ragas_llm = LangchainLLMWrapper(lc_llm)
    ragas_embeddings = LangchainEmbeddingsWrapper(lc_embeddings)
    metrics = _build_ragas_metrics(ragas_llm, ragas_embeddings)
    ragas_max_workers = _parse_ragas_max_workers()
    run_config = RunConfig(
        max_workers=ragas_max_workers,
        timeout=420,
        max_retries=12,
        max_wait=120,
        log_tenacity=True,
    )

    client = Client()
    ds_name = _dataset_name()
    limit = _parse_eval_limit()
    examples = list(_examples_for_eval(client, ds_name, limit))
    if not examples:
        raise EvaluationError(
            f"Нет примеров в датасете LangSmith «{ds_name}». "
            f"Загрузите набор командой dataset-upload или укажите LANGSMITH_DATASET_NAME."
        )

    logger.info(
        "RAGAS eval: LangSmith dataset=%s, примеров=%s, ragas_llm=%s ragas_emb=%s",
        ds_name,
        len(examples),
        ragas_llm_id,
        emb_raw,
    )

    target_fn = _make_rag_target(rag_runner)

    ls_results = client.evaluate(
        target_fn,
        data=iter(examples),
        evaluators=[],
        experiment_prefix="aidd-ragas",
        metadata={
            "pipeline": "aidd.telegram_rag",
            "dataset": ds_name,
            "ragas_llm": ragas_llm_id,
            "ragas_embedding": emb_raw,
        },
        max_concurrency=1,
        blocking=False,
    )

    rows: list[dict[str, Any]] = []
    for item in ls_results:
        run = item["run"]
        example = item["example"]
        question = ""
        if run.inputs:
            question = str(run.inputs.get("question") or "").strip()
        answer = ""
        documents: Any = []
        if run.outputs:
            answer = str(run.outputs.get("answer") or "").strip()
            documents = run.outputs.get("documents") or []
        ground_truth = ""
        if example.outputs:
            ground_truth = str(example.outputs.get("answer") or "").strip()
        contexts = _documents_to_contexts(documents)
        rows.append(
            {
                "question": question,
                "answer": answer,
                "contexts": contexts,
                "ground_truth": ground_truth,
                "run_id": str(run.id),
            }
        )

    ls_results.wait()

    if not rows:
        raise EvaluationError("Эксперимент LangSmith не вернул строк — прервать нельзя.")

    ragas_ds = HFDataset.from_dict(
        {
            "question": [r["question"] for r in rows],
            "answer": [r["answer"] for r in rows],
            "contexts": [r["contexts"] for r in rows],
            "ground_truth": [r["ground_truth"] for r in rows],
        }
    )

    n_metrics = len(metrics)
    n_tasks = len(rows) * n_metrics
    show_pb = _parse_ragas_show_progress()
    logger.info(
        "RAGAS: %s примеров × %s метрик = %s асинх-задач (max_workers=%s, tqdm=%s). "
        "С progress bar счётчик обновляется только после целой задачи — долго на 0%% норма; "
        "по логам httpx видно живые запросы.",
        len(rows),
        n_metrics,
        n_tasks,
        ragas_max_workers,
        show_pb,
    )

    ragas_result = ragas_evaluate(
        ragas_ds,
        metrics=metrics,
        llm=ragas_llm,
        embeddings=ragas_embeddings,
        run_config=run_config,
        show_progress=show_pb,
    )
    scores_list = ragas_result.scores
    if len(scores_list) != len(rows):
        logger.warning(
            "RAGAS: число строк scores (%s) != числу run (%s)",
            len(scores_list),
            len(rows),
        )

    feedback_n = 0
    for idx, score_row in enumerate(scores_list):
        if idx >= len(rows):
            break
        run_id = rows[idx]["run_id"]
        for name in METRIC_NAMES:
            if name not in score_row:
                continue
            fv = _safe_float(score_row.get(name))
            if fv is None:
                continue
            try:
                client.create_feedback(
                    run_id=run_id,
                    key=name,
                    score=fv,
                    comment=f"RAGAS: {name}",
                )
                feedback_n += 1
            except Exception as e:
                logger.warning("create_feedback %s run %s: %s", name, run_id, e)

    means: dict[str, float | None] = {n: None for n in METRIC_NAMES}
    for name in METRIC_NAMES:
        vals: list[float] = []
        for srow in scores_list:
            fv = _safe_float(srow.get(name))
            if fv is not None:
                vals.append(fv)
        if vals:
            means[name] = sum(vals) / len(vals)

    exp_name = ls_results.experiment_name
    url = ls_results.comparison_url

    return EvaluationRunSummary(
        num_examples=len(rows),
        means=means,
        experiment_name=exp_name,
        comparison_url=url,
        feedback_rows=feedback_n,
    )


def format_summary_for_telegram(s: EvaluationRunSummary) -> str:
    lines = [
        f"Оценка RAG (RAGAS), примеров: {s.num_examples}",
        f"Эксперимент LangSmith: {s.experiment_name}",
        f"Feedback записей: {s.feedback_rows}",
    ]
    if s.comparison_url:
        lines.append(f"Сравнение: {s.comparison_url}")
    lines.append("")
    lines.append("Средние метрики:")
    for name in METRIC_NAMES:
        m = s.means.get(name)
        lines.append(f"  {name}: {m:.3f}" if m is not None else f"  {name}: —")
    return "\n".join(lines)
