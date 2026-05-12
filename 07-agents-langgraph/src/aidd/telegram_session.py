"""HTTP-сессия для Bot: trust_env=True — учитываются HTTPS_PROXY/HTTP_PROXY из окружения (VPN, локальный прокси)."""

from __future__ import annotations

import socket
from typing import Any

from aiohttp import ClientSession
from aiohttp.hdrs import USER_AGENT
from aiohttp.http import SERVER_SOFTWARE

from aiogram.__meta__ import __version__ as aiogram_version
from aiogram.client.session.aiohttp import AiohttpSession

from aidd.docker_context import is_docker_container


class TrustEnvAiohttpSession(AiohttpSession):
    """Как AiohttpSession, но ClientSession(..., trust_env=True) — иначе Python не ходит тем же путём, что браузер за VPN."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        # В контейнере host.docker.internal иногда резолвится в IPv6 без маршрута; IPv4 стабильнее.
        if is_docker_container() and "family" not in self._connector_init:
            self._connector_init = {**self._connector_init, "family": socket.AF_INET}
            self._should_reset_connector = True

    async def create_session(self) -> ClientSession:
        if self._should_reset_connector:
            await self.close()

        if self._session is None or self._session.closed:
            self._session = ClientSession(
                connector=self._connector_type(**self._connector_init),
                headers={
                    USER_AGENT: f"{SERVER_SOFTWARE} aiogram/{aiogram_version}",
                },
                trust_env=True,
            )
            self._should_reset_connector = False

        return self._session
