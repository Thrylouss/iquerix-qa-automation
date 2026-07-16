"""
Клиент для эндпоинтов iQuaRix OS, требующих авторизацию (Bearer-токен),
плюс /auth/verify, который эту авторизацию выдаёт.

Токен по умолчанию (`default_token`) не хардкодится — он выставляется
динамически фикстурой `auth_session` (conftest.py) после реального
/auth/login -> /auth/verify флоу на тестовом номере с фиксированным OTP.
См. shared/config/test_accounts.py.
"""
from typing import Any, Optional

import requests

from backend_tests.shared.http.base_client import BaseApiClient


class OsAuthenticatedClient(BaseApiClient):
    VERIFY_PATH = "/auth/verify"
    ME_PATH = "/auth/me"
    STATICS_TODAY_PATH = "/s/statics/today"
    OPERATIONS_PATH = "/s/operation/"
    OPERATION_DRAFT_PATH = "/s/operation/draft"
    NOTIFICATIONS_PATH = "/notification/"
    FILE_PATH = "/file/"
    BRANCH_PATH = "/s/branch"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Выставляется через set_default_token() после успешного login+verify.
        self.default_token: Optional[str] = None

    def set_default_token(self, token: str) -> None:
        self.default_token = token

    def _auth_headers(self, token: Optional[Any]) -> dict:
        """
        token=False -> без Authorization вообще (для негативных тестов).
        token не передан (None) -> self.default_token, выставленный auth_session.
        token=<строка> -> используем переданный (битый/просроченный/чужой).
        """
        if token is False:
            return {}
        effective_token = token if token else self.default_token
        if not effective_token:
            raise RuntimeError(
                "default_token не выставлен: вызовите client.set_default_token(...) "
                "или используйте фикстуру auth_session перед обращением к защищённым эндпоинтам."
            )
        return {"Authorization": f"Bearer {effective_token}"}

    def _default_headers(self, token: Optional[Any], extra_headers: Optional[dict]) -> dict:
        """Заголовки для обычных JSON-запросов (Content-Type: application/json)."""
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "x-app-language": "ru",
            "x-app-version": "1.0.1",
        }
        headers.update(self._auth_headers(token))
        if extra_headers:
            headers.update(extra_headers)
        return headers

    def _multipart_headers(self, token: Optional[Any], extra_headers: Optional[dict]) -> dict:
        """
        Заголовки для multipart/form-data запросов (upload файлов) — БЕЗ
        Content-Type: requests сам проставит правильный boundary при передаче files=.
        """
        headers = {
            "Accept": "application/json",
            "x-app-language": "ru",
            "x-app-version": "1.0.1",
        }
        headers.update(self._auth_headers(token))
        if extra_headers:
            headers.update(extra_headers)
        return headers

    # ------------------------------------------------------------------ #
    # POST /auth/verify — подтверждение кода из SMS, выдача access/refresh
    # ------------------------------------------------------------------ #
    def verify(
        self,
        phone_number: Optional[str] = "998998987882",
        code: Optional[str] = "10057",
        signature: Optional[str] = "c48dae889bec66654a81f39ea1fe67a238c4b8db960fde00ab3d58240138bff7",
        context: Optional[str] = "service",
        raw_body: Optional[Any] = None,
        omit_fields: Optional[list] = None,
        extra_headers: Optional[dict] = None,
    ) -> requests.Response:
        if raw_body is not None:
            body = raw_body
        else:
            body = {"phone_number": phone_number, "code": code, "signature": signature, "context": context}
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

        if isinstance(raw_body, (str, bytes)):
            return self.post(self.VERIFY_PATH, data=raw_body, headers=headers)
        return self.post(self.VERIFY_PATH, json=body, headers=headers)

    # ------------------------------------------------------------------ #
    # GET /auth/me — профиль текущего авторизованного пользователя
    # ------------------------------------------------------------------ #
    def me(self, token: Optional[Any] = None, extra_headers: Optional[dict] = None) -> requests.Response:
        """token=False -> без заголовка Authorization вообще."""
        headers = self._default_headers(token, extra_headers)
        return self.get(self.ME_PATH, headers=headers)

    # ------------------------------------------------------------------ #
    # GET /s/statics/today — дашборд-статистика сервиса за сегодня
    # ------------------------------------------------------------------ #
    def statics_today(self, token: Optional[Any] = None, extra_headers: Optional[dict] = None) -> requests.Response:
        headers = self._default_headers(token, extra_headers)
        return self.get(self.STATICS_TODAY_PATH, headers=headers)

    # ------------------------------------------------------------------ #
    # GET /s/operation/ — список заявок/операций сервиса с фильтром по статусам
    # ------------------------------------------------------------------ #
    def operations(
        self,
        statuses: Optional[list] = None,
        page: Optional[int] = 1,
        token: Optional[Any] = None,
        extra_headers: Optional[dict] = None,
        raw_params: Optional[dict] = None,
    ) -> requests.Response:
        headers = self._default_headers(token, extra_headers)
        params = raw_params if raw_params is not None else {"statuses": statuses or [], "page": page}
        return self.get(self.OPERATIONS_PATH, headers=headers, params=params)

    # ------------------------------------------------------------------ #
    # GET /notification/ — список уведомлений пользователя
    # ------------------------------------------------------------------ #
    def notifications(self, token: Optional[Any] = None, extra_headers: Optional[dict] = None) -> requests.Response:
        headers = self._default_headers(token, extra_headers)
        return self.get(self.NOTIFICATIONS_PATH, headers=headers)

    # ------------------------------------------------------------------ #
    # POST /file/ — загрузка файла (multipart/form-data)
    # ------------------------------------------------------------------ #
    # Минимальный валидный PNG (1x1 прозрачный пиксель) — достаточно, чтобы
    # пройти серверную валидацию "это изображение", не гоняя реальные тяжёлые файлы.
    _MINIMAL_PNG_BYTES = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
        b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
    )

    def upload_file(
        self,
        file_bytes: Optional[bytes] = None,
        filename: str = "test_image.png",
        mime_type: str = "image/png",
        purpose: Optional[str] = "service_image",
        token: Optional[Any] = None,
        extra_headers: Optional[dict] = None,
        omit_file: bool = False,
        omit_purpose: bool = False,
    ) -> requests.Response:
        headers = self._multipart_headers(token, extra_headers)
        data = {} if omit_purpose else {"purpose": purpose}
        files = {} if omit_file else {"file": (filename, file_bytes or self._MINIMAL_PNG_BYTES, mime_type)}
        return self.post(self.FILE_PATH, headers=headers, data=data, files=files)

    # ------------------------------------------------------------------ #
    # POST /s/branch — создание филиала сервиса
    # GET  /s/branch — список филиалов сервиса
    # ------------------------------------------------------------------ #
    def create_branch(
        self,
        payload: Optional[dict] = None,
        token: Optional[Any] = None,
        extra_headers: Optional[dict] = None,
    ) -> requests.Response:
        """
        payload по умолчанию не задаётся здесь намеренно — реальная полная
        структура (service_types с sub-каталогом) слишком объёмная и
        специфична для окружения. См. REFERENCE_VALID_BRANCH_PAYLOAD
        в shared/config/branch_reference_payload.py — тесты берут её оттуда
        и точечно переопределяют нужные поля (deepcopy).
        """
        headers = self._default_headers(token, extra_headers)
        return self.post(self.BRANCH_PATH, json=payload, headers=headers)

    def list_branches(self, token: Optional[Any] = None, extra_headers: Optional[dict] = None) -> requests.Response:
        headers = self._default_headers(token, extra_headers)
        return self.get(self.BRANCH_PATH, headers=headers)

    # ------------------------------------------------------------------ #
    # POST /s/operation/draft — создание черновика заявки на обслуживание
    # ------------------------------------------------------------------ #
    def create_operation_draft(
        self,
        vehicle_id: Optional[str] = None,
        service_branch_id: Optional[str] = None,
        raw_body: Optional[Any] = None,
        omit_fields: Optional[list] = None,
        token: Optional[Any] = None,
        extra_headers: Optional[dict] = None,
    ) -> requests.Response:
        if raw_body is not None:
            body = raw_body
        else:
            body = {"vehicle_id": vehicle_id, "service_branch_id": service_branch_id}
            for field in omit_fields or []:
                body.pop(field, None)
        headers = self._default_headers(token, extra_headers)
        return self.post(self.OPERATION_DRAFT_PATH, json=body, headers=headers)
