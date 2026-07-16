"""
Тесты POST /auth/login — iQuaRix OS.

Референс успешного запроса (из реального API-лога):
    body: {"phone_number": "998998987882", "context": "service"}
    -> 200 {"signature": "<hex>", "success": true}

Подтверждено живым прогоном:
  - Бэкенд рейт-лимитит /auth/login ПО НОМЕРУ ТЕЛЕФОНА: после успешного
    логина повторный вызов тем же номером в течение ~10 минут получает
        403 {"success": false, "statusCode": 403,
             "error": "TOO_MANY_REQUESTS_WAIT_10_MINUTES", "message": "..."}
  - Незарегистрированный номер (валидного формата) даёт
        403 {"success": false, "statusCode": 403,
             "error": "USER_NOT_IN_SYSTEM", "message": "..."}
  - Битый JSON в теле сейчас роняет бэкенд в 500 (см. TODO ниже — похоже на баг).
  - GET на /auth/login отдаёт 401 (видимо, auth-guard отрабатывает раньше роутинга).

ВАЖНО про rate-limit в этом файле:
  - Реальный valid_phone_number используется только ОДИН РАЗ за сессию —
    через фикстуру `successful_login_response` (conftest.py). Все проверки
    схемы/заголовков/времени переиспользуют этот один response, а не
    дёргают API заново.
  - Тест на сам rate-limit (TestLoginRateLimiting) сознательно делает
    второй вызов ПОСЛЕ этого — это единственное место, где мы специально
    сжигаем квоту второй раз.
  - Остальные негативные тесты используют либо заведомо невалидные номера
    (не проходят структурную валидацию, до рейт-лимита дело не доходит),
    либо отдельный "мусорный" номер, не пересекающийся с valid_phone_number.
"""
import jsonschema
import pytest

from backend_tests.shared.schemas.auth_schemas import LOGIN_SUCCESS_SCHEMA, LOGIN_ERROR_SCHEMA

pytestmark = [pytest.mark.os, pytest.mark.regression]

# Номер валидного формата, но заведомо не зарегистрированный в системе.
# Используется только здесь, чтобы не пересекаться по rate-limit с valid_phone_number.
NONEXISTENT_PHONE = "998900000000"

# "Мусорный" номер валидного формата для тестов, где важна валидация ДРУГИХ полей
# (context), а не самого номера/лимита. Не совпадает с valid_phone_number.
STRUCTURAL_TEST_PHONE = "998911111111"


# ---------------------------------------------------------------------------
# ПОЗИТИВНЫЕ СЦЕНАРИИ (используют закешированный единственный успешный вызов)
# ---------------------------------------------------------------------------

@pytest.mark.smoke
class TestLoginPositive:

    def test_login_success_returns_200_and_signature(self, successful_login_response):
        body = successful_login_response.json()
        assert body["success"] is True
        assert isinstance(body["signature"], str) and len(body["signature"]) > 0

    def test_login_response_matches_schema(self, successful_login_response):
        jsonschema.validate(instance=successful_login_response.json(), schema=LOGIN_SUCCESS_SCHEMA)

    def test_login_response_headers(self, successful_login_response):
        content_type = successful_login_response.headers.get("content-type", "")
        assert "application/json" in content_type

    def test_login_response_time_within_sla(self, successful_login_response):
        """Простейшая проверка производительности на том же закешированном вызове."""
        assert successful_login_response.elapsed.total_seconds() < 5, "Ответ auth/login занял более 5 секунд"

    def test_login_with_different_locale_header_is_accepted(self, os_auth_client):
        """
        Проверяем, что x-app-language не ломает обработку запроса — без траты
        квоты valid_phone_number: используем номер, не проходящий структурную
        проверку по факту существования, но это ОК — цель теста в заголовке,
        а не в успешном логине. Ожидаем корректный, не 500-й, ответ.
        """
        response = os_auth_client.login(
            phone_number=NONEXISTENT_PHONE,
            context="service",
            extra_headers={"x-app-language": "uz"},
        )
        assert response.status_code < 500
        assert "application/json" in response.headers.get("content-type", "")


# ---------------------------------------------------------------------------
# ОТДЕЛЬНЫЙ НАБОР: поведение rate-limit'а (сознательно тратит вторую попытку
# valid_phone_number за сессию — держим отдельно, чтобы не путать с regression)
# ---------------------------------------------------------------------------

@pytest.mark.regression
class TestLoginRateLimiting:

    def test_repeated_login_within_window_is_rate_limited(
        self, os_auth_client, valid_phone_number, successful_login_response
    ):
        """
        successful_login_response уже потратил один "успешный" вызов в этой
        сессии. Повторный вызов тем же номером должен быть отклонён лимитером,
        а не тихо зафейлиться где-то ещё.
        """
        second_response = os_auth_client.login(phone_number=valid_phone_number, context="service")

        assert second_response.status_code == 403
        body = second_response.json()
        jsonschema.validate(instance=body, schema=LOGIN_ERROR_SCHEMA)
        assert body["error"] == "TOO_MANY_REQUESTS_WAIT_10_MINUTES"
        assert body["success"] is False


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

    def test_login_without_context(self, os_auth_client):
        response = os_auth_client.login(phone_number=STRUCTURAL_TEST_PHONE, omit_fields=["context"])
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
        """Номер валидного формата, но не зарегистрированный в системе — подтверждено реальным ответом бэкенда."""
        response = os_auth_client.login(phone_number=NONEXISTENT_PHONE, context="service")

        assert response.status_code == 403, (
            f"Ожидался 403 USER_NOT_IN_SYSTEM, получено {response.status_code}: {response.text}"
        )
        body = response.json()
        jsonschema.validate(instance=body, schema=LOGIN_ERROR_SCHEMA)
        assert body["error"] == "USER_NOT_IN_SYSTEM"

    @pytest.mark.parametrize("bad_context", [
        "admin",          # чужой контекст (не относится к OS)
        "b2b",
        "SERVICE",        # регистронезависимость не гарантирована
        "",               # пустая строка
        123,              # неверный тип
        ["service"],      # неверный тип (массив)
    ])
    def test_login_with_invalid_context(self, os_auth_client, bad_context):
        response = os_auth_client.login(raw_body={"phone_number": STRUCTURAL_TEST_PHONE, "context": bad_context})
        assert response.status_code in (400, 422), (
            f"Context '{bad_context}' должен отклоняться, получено {response.status_code}: {response.text}"
        )

    def test_login_with_extra_unexpected_field(self, os_auth_client):
        """Лишнее поле в теле не должно ломать эндпоинт (но и не должно давать 500)."""
        response = os_auth_client.login(
            raw_body={
                "phone_number": STRUCTURAL_TEST_PHONE,
                "context": "service",
                "unexpected_field": "hacker_value",
            }
        )
        assert response.status_code < 500


# ---------------------------------------------------------------------------
# НЕГАТИВНЫЕ СЦЕНАРИИ: транспорт / протокол
# ---------------------------------------------------------------------------

class TestLoginTransportLevel:

    @pytest.mark.xfail(
        reason="Бэкенд сейчас отвечает 500 на битый JSON вместо 400/422 — похоже на баг, "
                "заведён вопрос бэкенд-команде. Тест документирует ожидаемое (корректное) поведение "
                "и должен стать зелёным сам собой, когда баг починят (тогда pytest покажет XPASS).",
        strict=False,
    )
    def test_login_with_malformed_json_body(self, os_auth_client):
        broken_json = '{"phone_number": "998998987882", "context": "service"'  # нет закрывающей скобки
        response = os_auth_client.login(raw_body=broken_json)
        assert response.status_code in (400, 422), (
            f"Битый JSON должен давать 400/422, получено {response.status_code}"
        )

    def test_login_with_wrong_content_type(self, os_auth_client):
        response = os_auth_client.login(
            phone_number=STRUCTURAL_TEST_PHONE,
            context="service",
            extra_headers={"Content-Type": "text/plain"},
        )
        assert response.status_code in (400, 415, 422), (
            f"Неверный Content-Type должен отклоняться, получено {response.status_code}"
        )

    def test_login_get_method_not_allowed(self, os_auth_client):
        """
        Эндпоинт задокументирован как POST. Реально бэкенд отдаёт 401 (похоже,
        auth-guard/middleware отрабатывает раньше роутинга и раньше проверки метода) —
        это тоже приемлемо: GET не должен успешно логинить.
        """
        response = os_auth_client.get("/auth/login")
        assert response.status_code in (401, 404, 405)

    def test_login_without_accept_header(self, os_auth_client):
        response = os_auth_client.login(
            phone_number=STRUCTURAL_TEST_PHONE,
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

    def test_login_xss_payload_in_context(self, os_auth_client):
        payload = "<script>alert(1)</script>"
        response = os_auth_client.login(raw_body={"phone_number": STRUCTURAL_TEST_PHONE, "context": payload})
        assert response.status_code in (400, 422)

    def test_login_response_does_not_leak_stack_trace(self, os_auth_client):
        """При любой ошибке ответ не должен содержать технических деталей (stack trace, SQL, путь к файлу)."""
        response = os_auth_client.login(raw_body={"phone_number": None, "context": None})
        text_lower = response.text.lower()
        leak_markers = ["traceback", "stacktrace", "at line", "sqlstate", "/var/", "exception in"]
        for marker in leak_markers:
            assert marker not in text_lower, f"Обнаружена утечка технической информации: '{marker}'"
