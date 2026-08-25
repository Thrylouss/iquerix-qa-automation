"""
Тесты POST /auth/login — iQuaRix B2B.

Референс успешного запроса (реальный лог, присланный пользователем):
    body: {"phone_number": "998017892235", "context": "fleet"}
    -> 200 {"signature": "<hex>", "success": true}

Тестовые номера (пул с фиксированным OTP 43431, config/test_accounts.py) —
используются СТРОГО для позитивных сценариев:
    998017892235, 998017893235
(998017891234 БОЛЬШЕ НЕ ИСПОЛЬЗУЕТСЯ — исключён из пула по указанию
пользователя.)

МЕХАНИКА ЛИМИТА /auth/login (см. api_clients/login_lock_tracker.py):
  - Повторный /auth/login в течение 30 сек после успешного -> 403
    {"error": "TOO_MANY_REQUESTS_WAIT_30_SECONDS"}.
  - Успешный /auth/verify после login СНИМАЕТ ограничение полностью.
  - Пока login "висит" неподтверждённым verify — блокируется НЕ ТОЛЬКО
    повторный login тем же номером, но и ЛЮБОЙ login другим номером на
    всю сессию/IP (403 TRY_AGAIN_LATER).

По этой причине здесь НЕТ отдельного теста, который намеренно бы триггерил
лимит (это создавало "висящий" login и каскадно ломало остальные тесты
через TRY_AGAIN_LATER). Вместо этого: successful_login_response (conftest.py)
СРАЗУ закрывается через verify сразу после получения — состояние никогда
не остаётся "висящим" ни на секунду, лимит не расходуется вообще, и любой
негативный/структурный тест ниже может выполняться сразу вслед, без риска
TRY_AGAIN_LATER.
"""
import jsonschema
import pytest

from backend_tests.iquerix_b2b.schemas.auth_schemas import LOGIN_ERROR_SCHEMA, LOGIN_SUCCESS_SCHEMA

pytestmark = [pytest.mark.b2b, pytest.mark.regression]

# Валидно ОТФОРМАТИРОВАННЫЙ (998 + 9 цифр), но не входящий в тестовый пул
# номер — используется для FORBIDDEN. НЕ входит в FIXED_OTP_TEST_PHONES.
NONEXISTENT_PHONE = "998900000099"

# Тоже валидный формат, для тестов, где важна валидация ДРУГИХ полей (context
# и т.п.), а не самого номера.
STRUCTURAL_TEST_PHONE = "998911111199"


# ---------------------------------------------------------------------------
# ПОЗИТИВНЫЕ СЦЕНАРИИ
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
        assert successful_login_response.elapsed.total_seconds() < 5, "Ответ auth/login занял более 5 секунд"


# ---------------------------------------------------------------------------
# НЕГАТИВНЫЕ СЦЕНАРИИ: отсутствующие / пустые поля
# (используют STRUCTURAL_TEST_PHONE или структурно невалидные значения —
# НЕ входят в тестовый пул, лимит не расходуют)
# ---------------------------------------------------------------------------

@pytest.mark.regression
class TestLoginMissingFields:

    def test_login_without_phone_number(self, b2b_auth_client):
        response = b2b_auth_client.login(context="fleet", omit_fields=["phone_number"])
        assert response.status_code in (400, 422), (
            f"Ожидалась ошибка валидации без phone_number, получено {response.status_code}: {response.text}"
        )
        assert response.json().get("success") is not True

    def test_login_without_context(self, b2b_auth_client):
        response = b2b_auth_client.login(phone_number=STRUCTURAL_TEST_PHONE, omit_fields=["context"])
        assert response.status_code in (400, 422), (
            f"Ожидалась ошибка валидации без context, получено {response.status_code}: {response.text}"
        )

    def test_login_with_empty_body(self, b2b_auth_client):
        response = b2b_auth_client.login(raw_body={})
        assert response.status_code in (400, 422)

    def test_login_with_empty_phone_number(self, b2b_auth_client):
        response = b2b_auth_client.login(phone_number="", context="fleet")
        assert response.status_code in (400, 422)

    def test_login_with_null_phone_number(self, b2b_auth_client):
        response = b2b_auth_client.login(raw_body={"phone_number": None, "context": "fleet"})
        assert response.status_code in (400, 422)


# ---------------------------------------------------------------------------
# НЕГАТИВНЫЕ СЦЕНАРИИ: невалидные значения полей (типичные ошибки юзера)
# ---------------------------------------------------------------------------

@pytest.mark.regression
class TestLoginInvalidValues:

    @pytest.mark.parametrize("bad_phone", [
        "123",                        # слишком короткий — юзер не дописал номер
        "abcdefghigk",                # буквы вместо цифр — вставил не туда
        "99801789123499999999999",    # слишком длинный — двойной ввод/copy-paste баг
        "+998 01 789 12 34",          # с форматированием — юзер скопировал из контактов
        " ",                           # только пробел
    ])
    def test_login_with_invalid_phone_format(self, b2b_auth_client, bad_phone):
        response = b2b_auth_client.login(phone_number=bad_phone, context="fleet")
        assert response.status_code in (400, 422), (
            f"Невалидный номер '{bad_phone}' должен отклоняться, получено {response.status_code}: {response.text}"
        )

    def test_login_with_nonexistent_phone_number(self, b2b_auth_client):
        """Валидный формат номера, но не зарегистрирован в системе — типичный сценарий опечатки."""
        response = b2b_auth_client.login(phone_number=NONEXISTENT_PHONE, context="fleet")
        assert response.status_code == 403, (
            f"Ожидался 403 FORBIDDEN, получено {response.status_code}: {response.text}"
        )
        body = response.json()
        jsonschema.validate(instance=body, schema=LOGIN_ERROR_SCHEMA)
        assert body["error"] == "FORBIDDEN"

    @pytest.mark.parametrize("bad_context", [
        "service",         # чужой контекст (не относится к B2B/fleet)
        "",                # пустая строка
        123,               # неверный тип
    ])
    def test_login_with_invalid_context(self, b2b_auth_client, bad_context):
        response = b2b_auth_client.login(raw_body={"phone_number": STRUCTURAL_TEST_PHONE, "context": bad_context})
        assert response.status_code in (400, 422), (
            f"Context '{bad_context}' должен отклоняться, получено {response.status_code}: {response.text}"
        )

    def test_login_with_extra_unexpected_field(self, b2b_auth_client):
        """Лишнее поле в теле не должно ломать эндпоинт (но и не должно давать 500)."""
        response = b2b_auth_client.login(
            raw_body={
                "phone_number": STRUCTURAL_TEST_PHONE,
                "context": "fleet",
                "unexpected_field": "hacker_value",
            }
        )
        assert response.status_code < 500


# ---------------------------------------------------------------------------
# НЕГАТИВНЫЕ СЦЕНАРИИ: транспорт / протокол
# ---------------------------------------------------------------------------

@pytest.mark.regression
class TestLoginTransportLevel:

    @pytest.mark.security
    @pytest.mark.xfail(
        reason="Не исключено, что бэкенд отвечает 500 на битый JSON вместо 400/422 "
                "(похоже на баг). Тест документирует ожидаемое (корректное) поведение "
                "и должен стать зелёным сам собой, если баг починят (тогда pytest покажет XPASS).",
        strict=False,
    )
    def test_login_with_malformed_json_body(self, b2b_auth_client):
        broken_json = '{"phone_number": "998911111199", "context": "fleet"'  # нет закрывающей скобки
        response = b2b_auth_client.login(raw_body=broken_json)
        assert response.status_code in (400, 422), (
            f"Битый JSON должен давать 400/422, получено {response.status_code}"
        )

    def test_login_with_wrong_content_type(self, b2b_auth_client):
        response = b2b_auth_client.login(
            phone_number=STRUCTURAL_TEST_PHONE,
            context="fleet",
            extra_headers={"Content-Type": "text/plain"},
        )
        assert response.status_code in (400, 415, 422), (
            f"Неверный Content-Type должен отклоняться, получено {response.status_code}"
        )

    def test_login_get_method_not_allowed(self, b2b_auth_client):
        response = b2b_auth_client.get("/auth/login")
        assert response.status_code in (401, 404, 405)

    def test_login_without_accept_header(self, b2b_auth_client):
        response = b2b_auth_client.login(
            phone_number=STRUCTURAL_TEST_PHONE,
            context="fleet",
            extra_headers={"Accept": "*/*"},
        )
        assert response.status_code < 500

    def test_login_with_outdated_app_version_returns_426(self, b2b_auth_client):
        """
        Подтверждено живым прогоном: устаревший x-app-version даёт
        426 UPDATE_REQUIRED с ссылками на сторы в meta.
        """
        response = b2b_auth_client.login(
            phone_number=STRUCTURAL_TEST_PHONE,
            context="fleet",
            extra_headers={"x-app-version": "0.0.1"},
        )
        assert response.status_code == 426, (
            f"Ожидался 426 UPDATE_REQUIRED для устаревшей версии, получено {response.status_code}: {response.text}"
        )
        body = response.json()
        assert body["error"] == "UPDATE_REQUIRED"
        assert body["meta"]["update_required"] is True


# ---------------------------------------------------------------------------
# НЕГАТИВНЫЕ СЦЕНАРИИ: безопасность (атакующие payload'ы)
# ---------------------------------------------------------------------------

@pytest.mark.regression
@pytest.mark.security
class TestLoginSecurity:

    def test_login_sql_injection_in_phone_number(self, b2b_auth_client):
        payload = "998911111199'; DROP TABLE users;--"
        response = b2b_auth_client.login(phone_number=payload, context="fleet")
        assert response.status_code in (400, 422), "SQL-инъекция должна отклоняться валидацией формата"
        assert response.status_code != 500, "Инъекция не должна приводить к 500 (утечка внутренней ошибки)"

    def test_login_xss_payload_in_context(self, b2b_auth_client):
        payload = "<script>alert(1)</script>"
        response = b2b_auth_client.login(raw_body={"phone_number": STRUCTURAL_TEST_PHONE, "context": payload})
        assert response.status_code in (400, 422)

    def test_login_response_does_not_leak_stack_trace(self, b2b_auth_client):
        response = b2b_auth_client.login(raw_body={"phone_number": None, "context": None})
        text_lower = response.text.lower()
        leak_markers = ["traceback", "stacktrace", "at line", "sqlstate", "/var/", "exception in"]
        for marker in leak_markers:
            assert marker not in text_lower, f"Обнаружена утечка технической информации: '{marker}'"

    def test_login_oversized_phone_number_does_not_crash_backend(self, b2b_auth_client):
        """Очень длинная строка в phone_number (потенциальный DoS/переполнение буфера) не должна давать 500."""
        payload = "9" * 5000
        response = b2b_auth_client.login(phone_number=payload, context="fleet")
        assert response.status_code in (400, 413, 422), (
            f"Огромный payload должен отклоняться, получено {response.status_code}"
        )
