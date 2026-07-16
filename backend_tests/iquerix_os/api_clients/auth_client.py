"""
Клиент для /auth/* эндпоинтов iQuaRix OS.
"""
from typing import Any, Optional

import requests

from backend_tests.shared.http.base_client import BaseApiClient

RATE_LIMIT_ERROR_CODE = "TOO_MANY_REQUESTS_WAIT_10_MINUTES"


class OsAuthClient(BaseApiClient):
    LOGIN_PATH = "/auth/login"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Выставляется в True, как только клиент увидит фактический ответ
        # TOO_MANY_REQUESTS_WAIT_10_MINUTES — используется conftest'ом,
        # чтобы больше не дёргать этот номер и скипать зависящие тесты,
        # а не заваливать их непонятными FAILED.
        self.rate_limited: bool = False

    def login(
        self,
        phone_number: Optional[str] = "998998987882",
        context: Optional[str] = "service",
        extra_headers: Optional[dict] = None,
        raw_body: Optional[Any] = None,
        omit_fields: Optional[list] = None,
    ) -> requests.Response:
        """
        Отправляет запрос на /auth/login.

        - raw_body: если передан, отправляется как есть (для тестов "битого" JSON/тела).
        - omit_fields: список полей, которые нужно исключить из тела (для проверки required-валидации).
        """
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
            "x-app-version": "1.0.1",
        }
        if extra_headers:
            headers.update(extra_headers)

        # raw_body как строка/байты -> отправляем "как есть" через data (для тестов битого JSON)
        # raw_body как dict/None -> отправляем через json (requests сам сериализует и выставит content-length)
        if isinstance(raw_body, (str, bytes)):
            response = self.post(self.LOGIN_PATH, data=raw_body, headers=headers)
        else:
            response = self.post(self.LOGIN_PATH, json=body, headers=headers)

        self._track_rate_limit(response)
        return response

    def _track_rate_limit(self, response: requests.Response) -> None:
        if response.status_code != 403:
            return
        try:
            error_code = response.json().get("error")
        except ValueError:
            return
        if error_code == RATE_LIMIT_ERROR_CODE:
            self.rate_limited = True
