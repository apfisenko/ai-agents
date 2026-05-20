"""E2E: сопоставление траектории с эталоном инструментов (agentevals, superset + ignore args).

Детерминизм — в смысле проверки без «мнения» LLM-судьи; сама модель агента стохастична (temperature > 0).
Явные формулировки запросов снижают риск пропуска нужного tool.
"""

from __future__ import annotations

import pytest

from agentevals.trajectory.match import create_async_trajectory_match_evaluator

from tests.e2e.conftest import reference_must_call_tool, unique_thread_id


@pytest.mark.asyncio
async def test_trajectory_includes_rag_search_for_docs_question(e2e_bank_runner):
    eval_fn = create_async_trajectory_match_evaluator(
        trajectory_match_mode="superset",
        tool_args_match_mode="ignore",
    )
    tid = unique_thread_id("rag")
    await e2e_bank_runner.ainvoke_turn(
        chat_id=0,
        thread_id=tid,
        user_text=(
            "Обязательно вызови инструмент rag_search: найди в проиндексированных документах "
            "информацию о вкладах, ответь одним коротким предложением по сути."
        ),
    )
    messages = await e2e_bank_runner.aget_thread_messages(tid)
    ref = reference_must_call_tool("rag_search")
    result = await eval_fn(outputs=messages, reference_outputs=ref)
    assert result.get("score") is True, result


@pytest.mark.asyncio
async def test_trajectory_includes_convert_currency_for_amount(e2e_bank_runner):
    eval_fn = create_async_trajectory_match_evaluator(
        trajectory_match_mode="superset",
        tool_args_match_mode="ignore",
    )
    tid = unique_thread_id("fx")
    await e2e_bank_runner.ainvoke_turn(
        chat_id=0,
        thread_id=tid,
        user_text=(
            "Обязательно вызови инструмент convert_currency: переведи 100 USD в RUB, "
            "в ответе укажи число в рублях одной строкой."
        ),
    )
    messages = await e2e_bank_runner.aget_thread_messages(tid)
    ref = reference_must_call_tool("convert_currency")
    result = await eval_fn(outputs=messages, reference_outputs=ref)
    assert result.get("score") is True, result
