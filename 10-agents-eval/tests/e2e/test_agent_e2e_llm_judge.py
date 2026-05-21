"""E2E: LLM-as-a-Judge по траектории (agentevals). Модель судьи — AGENTEVALS_LLM_MODEL."""

from __future__ import annotations

import os

import pytest
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

from agentevals.trajectory.llm import TRAJECTORY_ACCURACY_PROMPT, create_async_trajectory_llm_as_judge

from aidd.config import AppConfig

from tests.e2e.conftest import unique_thread_id


@pytest.mark.asyncio
async def test_trajectory_llm_judge_coherent_rag_turn(e2e_bank_runner):
    load_dotenv(override=False)
    judge_model = (os.environ.get("AGENTEVALS_LLM_MODEL") or "").strip()
    if not judge_model:
        pytest.skip("Задайте AGENTEVALS_LLM_MODEL в .env для LLM-as-a-Judge e2e")

    cfg = AppConfig.from_env()
    # Не привязывать жёстко к LLM_MAX_COMPLETION_TOKENS чата: маленькое значение режет JSON
    # судьи (reasoning + "score": true/false) → OutputParserException.
    judge_max = max(1024, min(4096, cfg.llm_max_completion_tokens))
    judge_llm = ChatOpenAI(
        model=judge_model,
        api_key=cfg.open_api_key,
        base_url=cfg.open_base_url,
        temperature=0,
        max_tokens=judge_max,
    )
    evaluator = create_async_trajectory_llm_as_judge(
        prompt=TRAJECTORY_ACCURACY_PROMPT,
        judge=judge_llm,
    )

    tid = unique_thread_id("judge")
    await e2e_bank_runner.ainvoke_turn(
        chat_id=0,
        thread_id=tid,
        user_text="Кратко по документам: какие бывают сроки вкладов (rag_search)?",
    )
    messages = await e2e_bank_runner.aget_thread_messages(tid)
    result = await evaluator(outputs=messages)
    assert result.get("score") is True, result

@pytest.mark.asyncio
async def test_trajectory_llm_judge_convert_currency_turn(e2e_bank_runner):
    load_dotenv(override=False)
    judge_model = (os.environ.get("AGENTEVALS_LLM_MODEL") or "").strip()
    if not judge_model:
        pytest.skip("Задайте AGENTEVALS_LLM_MODEL в .env для LLM-as-a-Judge e2e")

    cfg = AppConfig.from_env()
    # Не привязывать жёстко к LLM_MAX_COMPLETION_TOKENS чата: маленькое значение режет JSON
    # судьи (reasoning + "score": true/false) → OutputParserException.
    judge_max = max(1024, min(4096, cfg.llm_max_completion_tokens))
    judge_llm = ChatOpenAI(
        model=judge_model,
        api_key=cfg.open_api_key,
        base_url=cfg.open_base_url,
        temperature=0,
        max_tokens=judge_max,
    )
    evaluator = create_async_trajectory_llm_as_judge(
        prompt=TRAJECTORY_ACCURACY_PROMPT,
        judge=judge_llm,
    )

    tid = unique_thread_id("judge_convert")
    await e2e_bank_runner.ainvoke_turn(
        chat_id=0,
        thread_id=tid,
        user_text="Переведи в рубли 100 долларов, в ответе укажи число в рублях одной строкой.",
    )
    messages = await e2e_bank_runner.aget_thread_messages(tid)
    result = await evaluator(outputs=messages)
    assert result.get("score") is True, result
