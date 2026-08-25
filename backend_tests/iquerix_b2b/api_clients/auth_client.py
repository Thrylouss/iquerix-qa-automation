"""
Клиент для /auth/login эндпоинта iQuaRix B2B.
"""
import os
from typing import Any, Optional

import requests

from backend_tests.iquerix_b2b.api_clients.login_lock_tracker import (
    mark_login_success,
    mark_rate_limited,
    wait_or_raise_if_locked,
)
from backend_tests.shared.http.base_client import BaseApiClient

# Минимальная версия приложения, которую принимает бэкенд (заголовок
# x-app-version) — подтверждено живым 426 UPDATE_REQUIRED ответом.
APP_VERSION = os.getenv("IQUERIX_B2B_APP_VERSION", "1.0.5")

# Тип приложения — подтверждено реальными запросами (curl) от пользователя:
# заголовок x-app-type: fleet присутствует во всех авторизованных запросах
# мобильного B2B-приложения. Раньше мы его не отправляли вообще — добавлен
# для консистентности с реальным клиентом.
APP_TYPE = os.getenv("IQUERIX_B2B_APP_TYPE", "fleet")

# Известные коды ограничения по частоте запросов на /auth/login —
# подтверждено живым прогоном пользователя.
RATE_LIMIT_ERROR_CODES = (
    "TOO_MANY_REQUESTS_WAIT_30_SECONDS",
    "TOO_MANY_REQUESTS_WAIT_10_MINUTES",
)


class B2bAuthClient(BaseApiClient):
    LOGIN_PATH = "/auth/login"

    def login(
        self,
        phone_number: Optional[str] = "998017892235",
        context: Optional[str] = "fleet",
        extra_headers: Optional[dict] = None,
        raw_body: Optional[Any] = None,
        omit_fields: Optional[list] = None,
        respect_lock: bool = True,
    ) -> requests.Response:
        """
        Отправляет запрос на /auth/login.

        - raw_body: если передан, отправляется как есть (для тестов "битого" JSON/тела).
        - omit_fields: список полей, которые нужно исключить из тела (для проверки required-валидации).
        - respect_lock: True (по умолчанию) — перед запросом ждём/проверяем
          локальный трекер ограничения ДЛЯ ЭТОГО НОМЕРА (см.
          login_lock_tracker.py). False — форсирует немедленный реальный
          запрос в обход трекера; используется ТОЛЬКО в тесте, который
          намеренно проверяет сам факт срабатывания ограничения.
        """
        # Номер, который реально уйдёт в теле запроса — используется и для
        # трекера лимита (raw_body с произвольным содержимым/строкой не
        # даёт чистого номера для отслеживания — в этом случае трекер
        # просто не используется, такие вызовы не расходуют лимит).
        effective_phone = None
        if raw_body is None:
            effective_phone = phone_number
        elif isinstance(raw_body, dict):
            candidate = raw_body.get("phone_number")
            effective_phone = candidate if isinstance(candidate, str) else None

        if respect_lock and effective_phone:
            wait_or_raise_if_locked(effective_phone)

        if raw_body is not None:
            body = raw_body
        else:
            body = {"phone_number": phone_number, "context": context}
            for field in omit_fields or []:
                body.pop(field, None)

        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "x-app-language": "ru",
            "x-app-type": APP_TYPE,
            "x-app-version": APP_VERSION,
        }
        if extra_headers:
            headers.update(extra_headers)

        if isinstance(raw_body, (str, bytes)):
            response = self.post(self.LOGIN_PATH, data=raw_body, headers=headers)
        else:
            response = self.post(self.LOGIN_PATH, json=body, headers=headers)

        if effective_phone:
            self._update_lock_tracker(response, effective_phone)
        return response

    def _update_lock_tracker(self, response: requests.Response, phone_number: str) -> None:
        """
        Помечаем блокировку ТОЛЬКО при успехе (200 — линия временно занята
        на 30 сек в ожидании verify) или при явном коде ограничения
        (403 WAIT_...). Для остальных ответов (400/422/403 FORBIDDEN/426 и
        т.д.) НИЧЕГО не помечаем — сервер отклоняет эти запросы ДО того,
        как добирается до анти-спам счётчика по номеру, значит и клиенту
        незачем считать этот номер "занятым".
        """
        if response.status_code == 200:
            mark_login_success(phone_number)
            return
        if response.status_code == 403:
            try:
                error_code = response.json().get("error")
            except ValueError:
                error_code = None
            if error_code in RATE_LIMIT_ERROR_CODES:
                mark_rate_limited(phone_number, error_code)
