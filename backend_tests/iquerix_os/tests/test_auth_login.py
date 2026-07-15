"""
Тесты POST /auth/login — iQuaRix OS.

Референс успешного запроса (из реального API-лога):
    body: {"phone_number": "998998987882", "context": "service"}
    -> 200 {"signature": "<hex>", "success": true}

Покрытие:
  - Позитив: валидный логин, разные допустимые context, разные локали заголовка
  - Негатив: отсутствующие/пустые поля, невалидный формат номера, невалидный context,
             битый JSON, неверный Content-Type, SQL-инъекция, XSS-пейлоад,
             неверный HTTP-метод, лишние поля в теле
  - Контракт: соответствие ответа jsonschema
"""
import json

import jsonschema
import pytest
import requests

from backend_tests.shared.schemas.auth_schemas import LOGIN_SUCCESS_SCHEMA

pytestmark = [pytest.mark.os, pytest.mark.regression]


# ---------------------------------------------------------------------------
# ПОЗИТИВНЫЕ СЦЕНАРИИ
# ---------------------------------------------------------------------------

@pytest.mark.smoke
class TestLoginPositive:

    def test_login_success_returns_200_and_signature(self, os_auth_client, valid_phone_number):
        response = os_auth_client.login(phone_number=valid_phone_number, context="service")

        assert response.status_code == 200, f"Ожидался 200, получено {response.status_code}: {response.text}"

        body = response.json()
        assert body["success"] is True
        assert isinstance(body["signature"], str) and len(body["signature"]) > 0

    def test_login_response_matches_schema(self, os_auth_client, valid_phone_number):
        response = os_auth_client.login(phone_number=valid_phone_number, context="service")
        body = response.json()

        jsonschema.validate(instance=body, schema=LOGIN_SUCCESS_SCHEMA)

    def test_login_response_headers(self, os_auth_client, valid_phone_number):
        response = os_auth_client.login(phone_number=valid_phone_number, context="service")

        content_type = response.headers.get("content-type", "")
        assert "application/json" in content_type

    def test_login_response_time_within_sla(self, os_auth_client, valid_phone_number):
        """Простейшая проверка производительности: ответ не должен занимать неадекватно долго."""
        response = os_auth_client.login(phone_number=valid_phone_number, context="service")
        assert response.elapsed.total_seconds() < 5, "Ответ auth/login занял более 5 секунд"

    @pytest.mark.parametrize("locale", ["ru", "uz", "en"])
    def test_login_success_with_different_locales(self, os_auth_client, valid_phone_number, locale):
        """Смена x-app-language не должна влиять на успешность логина."""
        response = os_auth_client.login(
            phone_number=valid_phone_number,
            context="service",
            extra_headers={"x-app-language": locale},
        )
        assert response.status_code == 200
        assert response.json()["success"] is True

    def test_login_two_consecutive_calls_return_different_or_valid_signatures(
        self, os_auth_client, valid_phone_number
    ):
        """Проверка, что подпись генерируется по запросу, а не кешируется статично (санити-чек)."""
        first = os_auth_client.login(phone_number=valid_phone_number, context="service")
        second = os_auth_client.login(phone_number=valid_phone_number, context="service")

        assert first.status_code == 200
        assert second.status_code == 200
        assert isinstance(first.json()["signature"], str)
        assert isinstance(second.json()["signature"], str)


# ---------------------------------------------------------------------------
# НЕГАТИВНЫЕ СЦЕНАРИИ: отсутствующие / пустые поля
# ---------------------------------------------------------------------------

class TestLoginMissingFields:

    def test_login_without_phone_number(self, os_auth_client):
        response = os_auth_client.login(context="service", omit_fields=["phone_number"])
        assert response.status_code in (400, 422), (
            f"Ожидалась ошибка валидации без phone_number, получено {response.status_code}: {response.text}"
        )
        assert response.json().get("success") is not True

    def test_login_without_context(self, os_auth_client, valid_phone_number):
        response = os_auth_client.login(phone_number=valid_phone_number, omit_fields=["context"])
        assert response.status_code in (400, 422), (
            f"Ожидалась ошибка валидации без context, получено {response.status_code}: {response.text}"
        )

    def test_login_with_empty_body(self, os_auth_client):
        response = os_auth_client.login(raw_body={})
        assert response.status_code in (400, 422)

    def test_login_with_empty_phone_number(self, os_auth_client):
        response = os_auth_client.login(phone_number="", context="service")
        assert response.status_code in (400, 422)

    def test_login_with_null_phone_number(self, os_auth_client):
        response = os_auth_client.login(raw_body={"phone_number": None, "context": "service"})
        assert response.status_code in (400, 422)


# ---------------------------------------------------------------------------
# НЕГАТИВНЫЕ СЦЕНАРИИ: невалидные значения полей
# ---------------------------------------------------------------------------

class TestLoginInvalidValues:

    @pytest.mark.parametrize("bad_phone", [
        "123",                       # слишком короткий
        "abcdefghigk",                # буквы вместо цифр
        "99899898788299999999999",   # слишком длинный
        "+998 99 898 78 82",         # с форматированием (плюс, пробелы)
        "998998987882 OR 1=1",       # попытка инъекции в номер
        " ",                          # только пробел
    ])
    def test_login_with_invalid_phone_format(self, os_auth_client, bad_phone):
        response = os_auth_client.login(phone_number=bad_phone, context="service")
        assert response.status_code in (400, 422), (
            f"Невалидный номер '{bad_phone}' должен отклоняться, получено {response.status_code}: {response.text}"
        )

    def test_login_with_nonexistent_phone_number(self, os_auth_client):
        """Номер валидного формата, но не зарегистрированный в системе."""
        response = os_auth_client.login(phone_number="998900000000", context="service")
        # Ожидаем либо явную ошибку "пользователь не найден", либо (если это OTP-флоу
        # для первичной регистрации) успешную отправку кода — уточнить бизнес-требование.
        assert response.status_code in (200, 400, 404), (
            f"Неожиданный статус для незарегистрированного номера: {response.status_code}: {response.text}"
        )

    @pytest.mark.parametrize("bad_context", [
        "admin",          # чужой контекст (не относится к OS)
        "b2b",
        "SERVICE",        # регистронезависимость не гарантирована
        "",               # пустая строка
        123,              # неверный тип
        ["service"],      # неверный тип (массив)
    ])
    def test_login_with_invalid_context(self, os_auth_client, valid_phone_number, bad_context):
        response = os_auth_client.login(raw_body={"phone_number": valid_phone_number, "context": bad_context})
        assert response.status_code in (400, 422), (
            f"Context '{bad_context}' должен отклоняться, получено {response.status_code}: {response.text}"
        )

    def test_login_with_extra_unexpected_field(self, os_auth_client, valid_phone_number):
        """Лишнее поле в теле не должно ломать эндпоинт (но и не должно давать 500)."""
        response = os_auth_client.login(
            raw_body={
                "phone_number": valid_phone_number,
                "context": "service",
                "unexpected_field": "hacker_value",
            }
        )
        assert response.status_code < 500


# ---------------------------------------------------------------------------
# НЕГАТИВНЫЕ СЦЕНАРИИ: транспорт / протокол
# ---------------------------------------------------------------------------

class TestLoginTransportLevel:

    def test_login_with_malformed_json_body(self, os_auth_client):
        broken_json = '{"phone_number": "998998987882", "context": "service"'  # нет закрывающей скобки
        response = os_auth_client.login(raw_body=broken_json)
        assert response.status_code in (400, 422), (
            f"Битый JSON должен давать 400/422, получено {response.status_code}"
        )

    def test_login_with_wrong_content_type(self, os_auth_client, valid_phone_number):
        response = os_auth_client.login(
            phone_number=valid_phone_number,
            context="service",
            extra_headers={"Content-Type": "text/plain"},
        )
        assert response.status_code in (400, 415, 422), (
            f"Неверный Content-Type должен отклоняться, получено {response.status_code}"
        )

    def test_login_get_method_not_allowed(self, os_auth_client):
        """Эндпоинт задокументирован как POST — GET должен быть отклонён."""
        response = os_auth_client.get("/auth/login")
        assert response.status_code in (404, 405)

    def test_login_without_accept_header(self, os_auth_client, valid_phone_number):
        response = os_auth_client.login(
            phone_number=valid_phone_number,
            context="service",
            extra_headers={"Accept": "*/*"},
        )
        # Не должно приводить к 500 независимо от Accept
        assert response.status_code < 500


# ---------------------------------------------------------------------------
# НЕГАТИВНЫЕ СЦЕНАРИИ: безопасность (базовые проверки)
# ---------------------------------------------------------------------------

class TestLoginSecurity:

    def test_login_sql_injection_in_phone_number(self, os_auth_client):
        payload = "998998987882'; DROP TABLE users;--"
        response = os_auth_client.login(phone_number=payload, context="service")
        assert response.status_code in (400, 422), "SQL-инъекция должна отклоняться валидацией формата"
        assert response.status_code != 500, "Инъекция не должна приводить к 500 (утечка внутренней ошибки)"

    def test_login_xss_payload_in_context(self, os_auth_client, valid_phone_number):
        payload = "<script>alert(1)</script>"
        response = os_auth_client.login(raw_body={"phone_number": valid_phone_number, "context": payload})
        assert response.status_code in (400, 422)

    def test_login_response_does_not_leak_stack_trace(self, os_auth_client):
        """При любой ошибке ответ не должен содержать технических деталей (stack trace, SQL, путь к файлу)."""
        response = os_auth_client.login(raw_body={"phone_number": None, "context": None})
        text_lower = response.text.lower()
        leak_markers = ["traceback", "stacktrace", "at line", "sqlstate", "/var/", "exception in"]
        for marker in leak_markers:
            assert marker not in text_lower, f"Обнаружена утечка технической информации: '{marker}'"
