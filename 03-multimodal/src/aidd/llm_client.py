from __future__ import annotations

import base64
import json
import logging
import re
from typing import Any

import httpx
from openai import AsyncOpenAI
from pydantic import ValidationError

from aidd.transaction_schema import TransactionExtractionResponse

logger = logging.getLogger(__name__)


def _http_err_suffix(exc: BaseException) -> str:
    sc = getattr(exc, "status_code", None)
    return f" http={sc}" if sc is not None else ""


def _exc_log_fragment(exc: BaseException, limit: int = 220) -> str:
    """Краткая строка для лога без многострочного шума (не содержимое чека целиком)."""
    s = str(exc).replace("\n", " ").strip()
    if len(s) > limit:
        return s[: limit - 1] + "…"
    return s


def _assistant_message_combined_text(msg: Any) -> str:
    """Поле content и при пустом — дополнительные поля ответа (reasoning/OpenRouter)."""
    primary = (getattr(msg, "content", None) or "").strip()
    if primary:
        return primary
    merged: dict[str, Any] = {}
    if hasattr(msg, "model_dump"):
        merged.update(msg.model_dump(mode="python"))
    elif hasattr(msg, "dict"):  # pragma: no cover
        merged.update(msg.dict())
    extra = getattr(msg, "__pydantic_extra__", None)
    if isinstance(extra, dict):
        merged.update(extra)
    for key in ("reasoning", "reasoning_content", "thinking", "reasoning_details"):
        v = merged.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()
        if isinstance(v, list):
            parts: list[str] = []
            for el in v:
                if isinstance(el, str) and el.strip():
                    parts.append(el.strip())
                elif isinstance(el, dict):
                    for sub in ("text", "content", "reasoning"):
                        t = el.get(sub)
                        if isinstance(t, str) and t.strip():
                            parts.append(t.strip())
                            break
            joined = "\n".join(parts).strip()
            if joined:
                return joined
    return ""

_RECEIPT_IMAGE_INSTRUCTION = (
    "На изображении чек или фискальный документ (или их скан). Извлеки все финансовые операции "
    "строго по правилам системного промпта и верни structured-ответ той же схемой."
)
_JSON_TAIL_PARSE = (
    "\n\nОтветь одним JSON-объектом с полями transactions (массив объектов операций) и reply_to_user "
    "(строка). Без markdown, без текста до или после JSON."
)
_TEXT_JSON_FALLBACK_HINT = (
    "\n\nОтветь одним JSON-объектом с полями transactions и reply_to_user по системному промпту. "
    "Без markdown и без текста вне JSON."
)


class LlmInvocationError(Exception):
    """Сбой вызова LLM; пользовательское сообщение формирует handler."""


def _strip_think_and_noise(text: str) -> str:
    """Убирает типичные блоки reasoning-моделей до основного JSON."""
    t = text.strip()
    t = re.sub(
        r"<(think|thinking|reasoning)>[\s\S]*?</\1>",
        "",
        t,
        flags=re.IGNORECASE,
    )
    return t.strip()


def _assistant_content_to_transaction_json(raw: str) -> TransactionExtractionResponse:
    """Разбирает JSON из ответа модели (прямой JSON или блок ```json … ```)."""
    text = _strip_think_and_noise((raw or "").strip())
    if not text:
        raise ValueError("empty assistant content")
    if "```" in text:
        start = text.find("```")
        rest = text[start + 3 :].lstrip()
        if rest.lower().startswith("json"):
            rest = rest[4:].lstrip()
        end = rest.rfind("```")
        if end != -1:
            text = rest[:end].strip()
        else:
            text = rest.strip()
    if not text.startswith("{"):
        i = text.find("{")
        j = text.rfind("}")
        if i != -1 and j != -1 and j > i:
            text = text[i : j + 1].strip()
    try:
        return TransactionExtractionResponse.model_validate_json(text)
    except (json.JSONDecodeError, ValidationError, ValueError) as e:
        raise ValueError(f"transaction JSON invalid: {_exc_log_fragment(e)}") from e


async def _extract_transactions_json_fallback(
    client: AsyncOpenAI,
    model: str,
    max_completion_tokens: int,
    system_prompt: str,
    messages: list[dict[str, str]],
) -> TransactionExtractionResponse:
    adj: list[dict[str, str]] = []
    for i, m in enumerate(messages):
        if i == len(messages) - 1 and m.get("role") == "user":
            adj.append(
                {
                    "role": "user",
                    "content": (m.get("content") or "") + _TEXT_JSON_FALLBACK_HINT,
                }
            )
        else:
            adj.append(dict(m))
    logger.info(
        "LLM request: extract_transactions json_object fallback, model=%s",
        model,
    )
    response = await client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            *adj,
        ],
        max_completion_tokens=max_completion_tokens,
        response_format={"type": "json_object"},
    )
    raw = (response.choices[0].message.content or "").strip()
    return _assistant_content_to_transaction_json(raw)


class LlmClient:
    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        max_completion_tokens: int,
        vision_model: str,
        vision_max_completion_tokens: int,
        http_timeout_seconds: float | None = None,
    ) -> None:
        self._model = model
        self._vision_model = vision_model
        self._max_completion_tokens = max_completion_tokens
        self._vision_max_completion_tokens = vision_max_completion_tokens
        client_kw: dict[str, Any] = {"api_key": api_key, "base_url": base_url}
        if http_timeout_seconds is not None:
            to = float(http_timeout_seconds)
            conn = min(30.0, to)
            client_kw["timeout"] = httpx.Timeout(timeout=to, connect=conn)
        self._client = AsyncOpenAI(**client_kw)

    async def complete(
        self,
        system_prompt: str,
        messages: list[dict[str, str]],
    ) -> str:
        try:
            logger.info("LLM request: complete, model=%s", self._model)
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    *messages,
                ],
                max_tokens=self._max_completion_tokens,
            )
        except Exception as e:
            logger.warning(
                "LLM complete failed: model=%s %s%s",
                self._model,
                type(e).__name__,
                _http_err_suffix(e),
            )
            raise LlmInvocationError from None

        choice = response.choices[0].message
        content = (choice.content or "").strip()
        if not content:
            logger.warning("LLM returned empty assistant message")
            raise LlmInvocationError
        return content

    async def extract_transactions(
        self,
        system_prompt: str,
        messages: list[dict[str, str]],
    ) -> TransactionExtractionResponse:
        """Structured output: список операций из текста и короткий ответ пользователю."""
        try:
            logger.info("LLM request: extract_transactions parse, model=%s", self._model)
            response = await self._client.chat.completions.parse(
                model=self._model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    *messages,
                ],
                max_completion_tokens=self._max_completion_tokens,
                response_format=TransactionExtractionResponse,
            )
        except Exception as e:
            logger.warning(
                "LLM structured parse failed: model=%s %s%s detail=%s",
                self._model,
                type(e).__name__,
                _http_err_suffix(e),
                _exc_log_fragment(e),
            )
            try:
                return await _extract_transactions_json_fallback(
                    self._client,
                    self._model,
                    self._max_completion_tokens,
                    system_prompt,
                    messages,
                )
            except Exception as e2:
                logger.warning(
                    "LLM json_object fallback failed: model=%s %s%s detail=%s",
                    self._model,
                    type(e2).__name__,
                    _http_err_suffix(e2),
                    _exc_log_fragment(e2),
                )
                raise LlmInvocationError from None

        choice = response.choices[0].message
        parsed = choice.parsed
        if parsed is None:
            logger.warning("LLM returned no parsed structured message")
            try:
                return await _extract_transactions_json_fallback(
                    self._client,
                    self._model,
                    self._max_completion_tokens,
                    system_prompt,
                    messages,
                )
            except Exception:
                raise LlmInvocationError from None
        return parsed

    async def extract_transactions_from_image(
        self,
        system_prompt: str,
        image_bytes: bytes,
        mime_type: str,
        caption_or_hint: str = "",
    ) -> TransactionExtractionResponse:
        """Изображение чека (VLM). OpenRouter/OpenAI-совместимые прокси часто не поддерживают
        chat.completions.parse для multimodal — используем create + JSON."""
        instruction = _RECEIPT_IMAGE_INSTRUCTION + _JSON_TAIL_PARSE
        cap = (caption_or_hint or "").strip()
        if cap:
            instruction = f"{instruction}\nКомментарий пользователя: {cap}"
        safe_mime = (mime_type or "image/jpeg").split(";")[0].strip().lower()
        if not safe_mime.startswith("image/"):
            safe_mime = "image/jpeg"
        b64 = base64.standard_b64encode(image_bytes).decode("ascii")
        data_url = f"data:{safe_mime};base64,{b64}"
        user_content: list[dict[str, Any]] = [
            {"type": "text", "text": instruction},
            {"type": "image_url", "image_url": {"url": data_url}},
        ]
        msgs: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]

        async def _call(with_json_object_mode: bool) -> TransactionExtractionResponse:
            logger.info(
                "LLM request: receipt vision, model=%s, json_object=%s, max_completion_tokens=%s",
                self._vision_model,
                with_json_object_mode,
                self._vision_max_completion_tokens,
            )
            kw: dict[str, Any] = {
                "model": self._vision_model,
                "messages": msgs,
                "max_completion_tokens": self._vision_max_completion_tokens,
            }
            if with_json_object_mode:
                kw["response_format"] = {"type": "json_object"}
            response = await self._client.chat.completions.create(**kw)
            msg = response.choices[0].message
            content = _assistant_message_combined_text(msg).strip()
            if not content:
                fr = getattr(response.choices[0], "finish_reason", None)
                logger.warning(
                    "VLM empty assistant text (content+extras): model=%s finish_reason=%s max_completion_tokens=%s",
                    self._vision_model,
                    fr,
                    self._vision_max_completion_tokens,
                )
                raise ValueError("empty assistant content after VLM response")
            return _assistant_content_to_transaction_json(content)

        try:
            return await _call(with_json_object_mode=True)
        except Exception as e1:
            logger.warning(
                "VLM json_object request failed: model=%s %s%s detail=%s",
                self._vision_model,
                type(e1).__name__,
                _http_err_suffix(e1),
                _exc_log_fragment(e1),
            )
            try:
                return await _call(with_json_object_mode=False)
            except Exception as e2:
                logger.warning(
                    "VLM fallback request failed: model=%s %s%s detail=%s",
                    self._vision_model,
                    type(e2).__name__,
                    _http_err_suffix(e2),
                    _exc_log_fragment(e2),
                )
                raise LlmInvocationError from None
