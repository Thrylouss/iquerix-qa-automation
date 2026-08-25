"""
Клиент для эндпоинтов iQuaRix B2B, требующих авторизацию (Bearer-токен),
плюс /auth/verify и /auth/refresh, которые эту авторизацию выдают/обновляют.

Токен по умолчанию (`default_token`) не хардкодится — он выставляется
динамически фикстурой `auth_session` (conftest.py) после реального
/auth/login -> /auth/verify флоу на тестовом номере с фиксированным OTP.
См. config/test_accounts.py.
"""
from typing import Any, Optional

import requests

from backend_tests.iquerix_b2b.api_clients.auth_client import APP_TYPE, APP_VERSION
from backend_tests.iquerix_b2b.api_clients.login_lock_tracker import mark_verify_success
from backend_tests.shared.http.base_client import BaseApiClient


class B2bAuthenticatedClient(BaseApiClient):
    VERIFY_PATH = "/auth/verify"
    REFRESH_PATH = "/auth/refresh"
    ME_PATH = "/auth/me"
    ME_SESSION_PATH = "/auth/me/session"
    NOTIFICATIONS_PATH = "/notification/"
    SERVICE_FILTER_PATH = "/service/filter"
    QR_PATH = "/qr/{code}"
    SHIFT_DRAFT_PATH = "/f/shift/draft"
    VEHICLE_PATH = "/f/vehicle/{vehicle_id}"
    SHIFT_READ_MILEAGE_PATH = "/f/shift/{shift_id}/read-mileage"
    SHIFT_START_PATH = "/f/shift/{shift_id}/start"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.default_token: Optional[str] = None
        self.default_refresh_token: Optional[str] = None

    def set_default_token(self, token: str) -> None:
        self.default_token = token

    def set_default_refresh_token(self, refresh_token: str) -> None:
        self.default_refresh_token = refresh_token

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
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "x-app-language": "ru",
            "x-app-type": APP_TYPE,
            "x-app-version": APP_VERSION,
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
        phone_number: Optional[str] = "998017892235",
        code: Optional[str] = "43431",
        signature: Optional[str] = "aed3e65f53b753be8ba0d28048e554fb56ab6b5969b454acda26fd1cda4df83c",
        context: Optional[str] = "fleet",
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
            "x-app-type": APP_TYPE,
            "x-app-version": APP_VERSION,
        }
        if extra_headers:
            headers.update(extra_headers)

        if isinstance(raw_body, (str, bytes)):
            response = self.post(self.VERIFY_PATH, data=raw_body, headers=headers)
        else:
            response = self.post(self.VERIFY_PATH, json=body, headers=headers)

        # КЛЮЧЕВОЙ момент подтверждённой механики: успешный verify снимает
        # ограничение /auth/login ДЛЯ ЭТОГО НОМЕРА полностью — следующий
        # login этим же номером открыт сразу.
        if response.status_code == 200 and isinstance(phone_number, str):
            mark_verify_success(phone_number)
        return response

    # ------------------------------------------------------------------ #
    # POST /auth/refresh — обновление пары access/refresh токенов
    # ------------------------------------------------------------------ #
    def refresh(
        self,
        refresh_token: Optional[Any] = None,
        raw_body: Optional[Any] = None,
        omit_fields: Optional[list] = None,
        extra_headers: Optional[dict] = None,
    ) -> requests.Response:
        """
        refresh_token не передан (None) -> self.default_refresh_token,
        выставленный auth_session.
        refresh_token=<строка> -> используем переданный (битый/просроченный/чужой).
        """
        if raw_body is not None:
            body = raw_body
        else:
            effective_token = refresh_token if refresh_token else self.default_refresh_token
            body = {"refresh_token": effective_token}
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
            return self.post(self.REFRESH_PATH, data=raw_body, headers=headers)
        return self.post(self.REFRESH_PATH, json=body, headers=headers)

    # ------------------------------------------------------------------ #
    # GET /auth/me — профиль текущего авторизованного пользователя
    # ------------------------------------------------------------------ #
    def me(self, token: Optional[Any] = None, extra_headers: Optional[dict] = None) -> requests.Response:
        """token=False -> без заголовка Authorization вообще (для негативных тестов)."""
        headers = self._default_headers(token, extra_headers)
        return self.get(self.ME_PATH, headers=headers)

    # ------------------------------------------------------------------ #
    # PUT /auth/me/session — регистрация/обновление сессии устройства
    # (push-токен FCM, доступы к геолокации/уведомлениям, инфо об устройстве)
    # ------------------------------------------------------------------ #
    # Референс реального тела запроса (curl пользователя):
    #   {"fcm": "<fcm token>", "location_access": "denied",
    #    "notification_access": "denied", "device_name": "iPhone iPhone",
    #    "lang": "ru", "rooted": false, "os_version": "26.6",
    #    "mobile_device_id": "<uuid>"}
    _DEFAULT_SESSION_PAYLOAD = {
        "fcm": "test_fcm_token_qa_automation",
        "location_access": "denied",
        "notification_access": "denied",
        "device_name": "QA Automation Device",
        "lang": "ru",
        "rooted": False,
        "os_version": "17.0",
        "mobile_device_id": "00000000-0000-0000-0000-000000000000",
    }

    def update_session(
        self,
        payload: Optional[dict] = None,
        raw_body: Optional[Any] = None,
        omit_fields: Optional[list] = None,
        token: Optional[Any] = None,
        extra_headers: Optional[dict] = None,
    ) -> requests.Response:
        """
        payload=None -> используется _DEFAULT_SESSION_PAYLOAD (безопасные
        тестовые значения, по структуре повторяющие реальный запрос).
        raw_body: если передан, отправляется как есть (для тестов "битого" тела).
        omit_fields: список полей, исключаемых из payload/_DEFAULT_SESSION_PAYLOAD
        (для проверки required-валидации).
        """
        headers = self._default_headers(token, extra_headers)

        if raw_body is not None:
            if isinstance(raw_body, (str, bytes)):
                return self.request("PUT", self.ME_SESSION_PATH, data=raw_body, headers=headers)
            body = raw_body
        else:
            body = dict(payload if payload is not None else self._DEFAULT_SESSION_PAYLOAD)
            for field in omit_fields or []:
                body.pop(field, None)

        return self.request("PUT", self.ME_SESSION_PATH, json=body, headers=headers)

    # ------------------------------------------------------------------ #
    # GET /notification/ — список уведомлений пользователя (пагинация)
    # ------------------------------------------------------------------ #
    def notifications(
        self,
        page: Optional[int] = 1,
        limit: Optional[int] = 10,
        token: Optional[Any] = None,
        extra_headers: Optional[dict] = None,
        raw_params: Optional[dict] = None,
    ) -> requests.Response:
        headers = self._default_headers(token, extra_headers)
        params = raw_params if raw_params is not None else {"page": page, "limit": limit}
        return self.get(self.NOTIFICATIONS_PATH, headers=headers, params=params)

    # ------------------------------------------------------------------ #
    # GET /service/filter — фильтры/справочник сервисов
    # ------------------------------------------------------------------ #
    def service_filter(
        self,
        token: Optional[Any] = None,
        extra_headers: Optional[dict] = None,
        params: Optional[dict] = None,
    ) -> requests.Response:
        headers = self._default_headers(token, extra_headers)
        return self.get(self.SERVICE_FILTER_PATH, headers=headers, params=params)

    # ------------------------------------------------------------------ #
    # GET /qr/{code} — распознавание QR-кода транспортного средства
    # ------------------------------------------------------------------ #
    def get_qr(
        self,
        code: str = "06FX40ZKENTAZ7VHKQS4916T3R",
        token: Optional[Any] = None,
        extra_headers: Optional[dict] = None,
    ) -> requests.Response:
        headers = self._default_headers(token, extra_headers)
        return self.get(self.QR_PATH.format(code=code), headers=headers)

    # ------------------------------------------------------------------ #
    # POST /f/shift/draft — создание черновика смены по QR-коду ТС
    # ------------------------------------------------------------------ #
    # Референс реального тела запроса (curl пользователя):
    #   {"vehicle_qr_code": "06FX40ZKENTAZ7VHKQS4916T3R",
    #    "lat_draft_start": 41.32292210708471, "long_draft_start": 69.2780259756387}
    def create_shift_draft(
        self,
        vehicle_qr_code: Optional[str] = "06FX40ZKENTAZ7VHKQS4916T3R",
        lat_draft_start: Optional[float] = 41.32292210708471,
        long_draft_start: Optional[float] = 69.2780259756387,
        raw_body: Optional[Any] = None,
        omit_fields: Optional[list] = None,
        token: Optional[Any] = None,
        extra_headers: Optional[dict] = None,
    ) -> requests.Response:
        headers = self._default_headers(token, extra_headers)

        if raw_body is not None:
            if isinstance(raw_body, (str, bytes)):
                return self.post(self.SHIFT_DRAFT_PATH, data=raw_body, headers=headers)
            body = raw_body
        else:
            body = {
                "vehicle_qr_code": vehicle_qr_code,
                "lat_draft_start": lat_draft_start,
                "long_draft_start": long_draft_start,
            }
            for field in omit_fields or []:
                body.pop(field, None)

        return self.post(self.SHIFT_DRAFT_PATH, json=body, headers=headers)

    # ------------------------------------------------------------------ #
    # GET /f/vehicle/{vehicle_id} — информация о транспортном средстве
    # ------------------------------------------------------------------ #
    def get_vehicle(
        self,
        vehicle_id: str = "01a018de-9d5e-71ae-9a8b-278950144411",
        token: Optional[Any] = None,
        extra_headers: Optional[dict] = None,
    ) -> requests.Response:
        headers = self._default_headers(token, extra_headers)
        return self.get(self.VEHICLE_PATH.format(vehicle_id=vehicle_id), headers=headers)

    # ------------------------------------------------------------------ #
    # POST /f/shift/{shift_id}/read-mileage — распознавание пробега по
    # фото одометра (multipart/form-data с файлом)
    # ------------------------------------------------------------------ #
    def read_mileage(
        self,
        shift_id: str,
        lat: Optional[float] = 41.32292210708471,
        long: Optional[float] = 69.2780259756387,
        claimed_mileage: Optional[int] = 85167,
        file_content: bytes = b"fake-image-bytes-for-qa-automation",
        file_name: str = "odometer.jpg",
        file_content_type: str = "image/jpeg",
        omit_fields: Optional[list] = None,
        include_file: bool = True,
        token: Optional[Any] = None,
        extra_headers: Optional[dict] = None,
    ) -> requests.Response:
        """
        multipart/form-data: lat/long/claimed_mileage как текстовые поля
        формы + file — файл (фото одометра). Content-Type НЕ выставляем
        руками — requests сам проставит multipart/form-data с boundary,
        когда передан параметр files.
        """
        # _default_headers() всегда ставит Content-Type: application/json —
        # для multipart-запроса это неверно, поэтому строим заголовки вручную,
        # без Content-Type (requests подставит правильный сам).
        headers = {
            "Accept": "application/json",
            "x-app-language": "ru",
            "x-app-type": APP_TYPE,
            "x-app-version": APP_VERSION,
        }
        headers.update(self._auth_headers(token))
        if extra_headers:
            headers.update(extra_headers)

        form_fields = {"lat": lat, "long": long, "claimed_mileage": claimed_mileage}
        for field in omit_fields or []:
            form_fields.pop(field, None)
        # requests ожидает строковые/байтовые значения в data для multipart —
        # None пропускаем, остальное приводим к строке.
        data = {k: str(v) for k, v in form_fields.items() if v is not None}

        files = {"file": (file_name, file_content, file_content_type)} if include_file else None

        path = self.SHIFT_READ_MILEAGE_PATH.format(shift_id=shift_id)
        return self.post(path, data=data, files=files, headers=headers)

    # ------------------------------------------------------------------ #
    # POST /f/shift/{shift_id}/start — старт смены
    # ------------------------------------------------------------------ #
    # Референс реального тела запроса (curl пользователя):
    #   {"started_at": "2026-08-25T00:17:49Z", "lat_start": 41.32292385044932,
    #    "long_start": 69.27802051539209, "is_everything_all_right_start": true,
    #    "mileage_start_approved_by_driver": true, "comment_start": ""}
    def start_shift(
        self,
        shift_id: str,
        started_at: Optional[str] = "2026-08-25T00:17:49Z",
        lat_start: Optional[float] = 41.32292385044932,
        long_start: Optional[float] = 69.27802051539209,
        is_everything_all_right_start: Optional[bool] = True,
        mileage_start_approved_by_driver: Optional[bool] = True,
        comment_start: Optional[str] = "",
        raw_body: Optional[Any] = None,
        omit_fields: Optional[list] = None,
        token: Optional[Any] = None,
        extra_headers: Optional[dict] = None,
    ) -> requests.Response:
        headers = self._default_headers(token, extra_headers)

        if raw_body is not None:
            if isinstance(raw_body, (str, bytes)):
                return self.post(
                    self.SHIFT_START_PATH.format(shift_id=shift_id), data=raw_body, headers=headers
                )
            body = raw_body
        else:
            body = {
                "started_at": started_at,
                "lat_start": lat_start,
                "long_start": long_start,
                "is_everything_all_right_start": is_everything_all_right_start,
                "mileage_start_approved_by_driver": mileage_start_approved_by_driver,
                "comment_start": comment_start,
            }
            for field in omit_fields or []:
                body.pop(field, None)

        return self.post(self.SHIFT_START_PATH.format(shift_id=shift_id), json=body, headers=headers)
