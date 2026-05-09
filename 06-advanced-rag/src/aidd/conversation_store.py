from __future__ import annotations

from typing import Dict, List

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage


class ConversationStore:
    """История диалога по chat_id только в памяти процесса (LangChain messages)."""

    def __init__(self) -> None:
        self._by_chat: Dict[int, List[BaseMessage]] = {}
        # Сумма total_tokens (как от провайдера) по успешным ответам за сессию чата.
        self._session_llm_total_tokens: Dict[int, int] = {}

    def get_messages(self, chat_id: int) -> List[BaseMessage]:
        return list(self._by_chat.get(chat_id, []))

    def append_user_message(self, chat_id: int, text: str) -> None:
        self._by_chat.setdefault(chat_id, []).append(HumanMessage(content=text))

    def append_assistant_message(self, chat_id: int, text: str) -> None:
        self._by_chat.setdefault(chat_id, []).append(AIMessage(content=text))

    def add_session_llm_total_tokens(self, chat_id: int, delta: int) -> int:
        """Учитывает total_tokens за один успешный ответ; возвращает накопительно по чату."""
        cur = self._session_llm_total_tokens.get(chat_id, 0) + max(0, delta)
        self._session_llm_total_tokens[chat_id] = cur
        return cur

    def clear(self, chat_id: int) -> None:
        self._by_chat.pop(chat_id, None)
        self._session_llm_total_tokens.pop(chat_id, None)
