from __future__ import annotations

import logging

from openai import AsyncOpenAI

logger = logging.getLogger(__name__)


class LlmInvocationError(Exception):
    """Сбой вызова LLM; пользовательское сообщение формирует handler."""


class LlmClient:
    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        max_completion_tokens: int,
    ) -> None:
        self._model = model
        self._max_completion_tokens = max_completion_tokens
        self._client = AsyncOpenAI(api_key=api_key, base_url=base_url)

    async def complete(
        self,
        system_prompt: str,
        messages: list[dict[str, str]],
    ) -> str:
        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    *messages,
                ],
                max_tokens=self._max_completion_tokens,
            )
        except Exception as e:
            logger.warning("LLM request failed: %s", type(e).__name__)
            raise LlmInvocationError from None

        choice = response.choices[0].message
        content = (choice.content or "").strip()
        if not content:
            logger.warning("LLM returned empty assistant message")
            raise LlmInvocationError
        return content
