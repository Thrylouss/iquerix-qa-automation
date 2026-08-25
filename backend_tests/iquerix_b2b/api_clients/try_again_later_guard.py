"""
Защита от ВТОРОГО, отдельного от TOO_MANY_REQUESTS_WAIT_30_SECONDS/10_MINUTES
(см. login_lock_tracker.py) механизма ограничения бэкенда.

ПОДТВЕРЖДЕНО живым прогоном: 403 (иногда 500) {"error": "TRY_AGAIN_LATER"}
появляется на /auth/login, /auth/verify И /auth/refresh — НЕЗАВИСИМО от
конкретного phone_number/refresh_token в теле запроса (в т.ч. на запросах
без номера вообще, например /auth/refresh). Значит это отдельный, более
широкий лимит на уровне IP/сессии на весь /auth/*, а не привязанный к
конкретному номеру телефона антиспам-счётчик OTP.

Эти два механизма ОРТОГОНАЛЬНЫ и обрабатываются раздельно:
  - login_lock_tracker.py: точная, по-номерная механика (30 сек / 10 мин),
    известная заранее — проверяется/ожидается ДО отправки запроса.
  - Этот модуль: реактивная защита от TRY_AGAIN_LATER, которая может
    прилететь на ЛЮБОЙ вызов /auth/* — реагируем ПОСЛЕ ответа сервера,
    ограниченным числом повторов с паузой.

СТРАТЕГИЯ:
  - Пауза перед повтором берётся из заголовка Retry-After ответа, если
    сервер его прислал (точное значение от сервера, не догадка).
  - Если заголовка нет — используем DEFAULT_RETRY_DELAY_SECONDS.
  - Не более MAX_RETRIES повторов на один вызов — если не помогло,
    возвращаем последний полученный ответ как есть (тест увидит реальный
    результат и корректно упадёт/пропустится с понятным сообщением, а не
    зависнет).

Настраивается через env, без правки кода:
    IQUERIX_B2B_TRY_AGAIN_RETRY_DELAY   (запасная пауза, по умолчанию 5 сек)
    IQUERIX_B2B_TRY_AGAIN_MAX_RETRIES   (по умолчанию 3 повтора)
"""
import os
import time

import requests

from backend_tests.shared.http.base_client import BaseApiClient

TRY_AGAIN_ERROR_CODE = "TRY_AGAIN_LATER"
DEFAULT_RETRY_DELAY_SECONDS = float(os.getenv("IQUERIX_B2B_TRY_AGAIN_RETRY_DELAY", "5"))
MAX_RETRIES = int(os.getenv("IQUERIX_B2B_TRY_AGAIN_MAX_RETRIES", "3"))


def _is_try_again_later(response: requests.Response) -> bool:
    if response.status_code not in (403, 500):
        return False
    try:
        return response.json().get("error") == TRY_AGAIN_ERROR_CODE
    except ValueError:
        return False


def _retry_delay_for(response: requests.Response) -> float:
    header_value = response.headers.get("Retry-After")
    if header_value:
        try:
            return float(header_value)
        except ValueError:
            pass
    return DEFAULT_RETRY_DELAY_SECONDS


class TryAgainLaterRetryMixin(BaseApiClient):
    """
    Переопределяет BaseApiClient.request() (общая точка входа для GET и
    POST) — прозрачно ретраит TRY_AGAIN_LATER для ЛЮБОГО вызова, вне
    зависимости от конкретного номера/токена в теле. Родитель для
    B2bAuthClient и B2bAuthenticatedClient вместо BaseApiClient напрямую.
    """

    def request(self, method: str, path: str, **kwargs) -> requests.Response:
        last_response = None
        for attempt in range(MAX_RETRIES + 1):
            response = super().request(method, path, **kwargs)
            last_response = response
            if not _is_try_again_later(response):
                return response
            if attempt < MAX_RETRIES:
                time.sleep(_retry_delay_for(response))
        return last_response
