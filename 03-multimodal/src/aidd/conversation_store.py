from __future__ import annotations

from typing import Dict, List


class ConversationStore:
    """История диалога по chat_id только в памяти процесса."""

    def __init__(self) -> None:
        self._by_chat: Dict[int, List[dict[str, str]]] = {}

    def get_messages(self, chat_id: int) -> List[dict[str, str]]:
        return list(self._by_chat.get(chat_id, []))

    def add_exchange(self, chat_id: int, user_text: str, assistant_text: str) -> None:
        msgs = self._by_chat.setdefault(chat_id, [])
        msgs.append({"role": "user", "content": user_text})
        msgs.append({"role": "assistant", "content": assistant_text})

    def clear(self, chat_id: int) -> None:
        self._by_chat.pop(chat_id, None)
