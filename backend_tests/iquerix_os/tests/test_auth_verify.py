"""
Тесты POST /auth/verify — подтверждение кода из SMS, выдача access/refresh токена.

Референс успешного запроса (реальный лог, ОДНОРАЗОВЫЙ код — для повторного
воспроизведения не годится):
    body: {"phone_number": "998998987882", "code": "10057",
           "signature": "c48dae889bec...", "context": "service"}
    -> 200 {"access_token": "...", "refresh_token": "...", "success": true}

С появлением пула тестовых номеров с ФИКСИРОВАННЫМ OTP-кодом (56563,
shared/config/test_accounts.py) появилась возможность гонять НАСТОЯЩИЙ
живой позитивный сценарий verify на каждом прогоне: /auth/login получает
свежий signature, /auth/verify с фиксированным кодом всегда его подтверждает.
"""
import jsonschema
import pytest

from backend_tests.shared.config.test_accounts import FIXED_OTP_CODE, VERIFY_TEST_PHONE
from backend_tests.shared.schemas.os_authenticated_schemas import VERIFY_SUCCESS_SCHEMA

pytestmark = [pytest.mark.os, pytest.mark.regression]

# Реальные, уже использованные (одноразовые) значения из исходного лога —
# годятся только для негативного теста "старый сигнатура больше не работает".
STALE_PHONE = "998998987882"
STALE_CODE = "10057"
STALE_SIGNATURE = "c48dae889bec66654a81f39ea1fe67a238c4b8db960fde00ab3d58240138bff7"


@pytest.fixture(scope="module")
def fresh_verify_response(os_auth_client, os_authenticated_client):
    """
    Живой позитивный флоу на отдельном номере пула (VERIFY_TEST_PHONE),
    независимом от AUTH_SESSION_PHONE (conftest.auth_session) и от
    LOGIN_TEST_PHONE (test_auth_login.py) — чтобы не делить rate-limit.
    """
    login_response = os_auth_client.login(phone_number=VERIFY_TEST_PHONE, context="service")
    if login_response.status_code != 200:
        pytest.skip(
            f"Не удалось получить signature для VERIFY_TEST_PHONE={VERIFY_TEST_PHONE}: "
            f"{login_response.status_code}: {login_response.text}. Возможно, номер под "
            f"rate-limit'ом — сдвиньте IQUERIX_OS_VERIFY_TEST_PHONE_INDEX."
        )
    signature = login_response.json()["signature"]

    return os_authenticated_client.verify(
        phone_number=VERIFY_TEST_PHONE, code=FIXED_OTP_CODE, signature=signature, context="service"
    ), signature


@pytest.mark.smoke
class TestVerifyPositive:

    def test_verify_with_fixed_otp_returns_200(self, fresh_verify_response):
        response, _ = fresh_verify_response
        assert response.status_code == 200, f"Получено {response.status_code}: {response.text}"
        assert response.json()["success"] is True

    def test_verify_response_matches_schema(self, fresh_verify_response):
        response, _ = fresh_verify_response
        jsonschema.validate(instance=response.json(), schema=VERIFY_SUCCESS_SCHEMA)

    def test_verify_returns_nonempty_tokens(self, fresh_verify_response):
        response, _ = fresh_verify_response
        body = response.json()
        assert len(body["access_token"]) > 20
        assert len(body["refresh_token"]) > 20
        assert body["access_token"] != body["refresh_token"]

    def test_verify_reusing_same_signature_twice_is_rejected(self, os_authenticated_client, fresh_verify_response):
        """Signature одноразовый: повторное использование того же (уже подтверждённого) signature должно отклоняться."""
        _, used_signature = fresh_verify_response
        second_attempt = os_authenticated_client.verify(
            phone_number=VERIFY_TEST_PHONE, code=FIXED_OTP_CODE, signature=used_signature, context="service"
        )
        assert second_attempt.status_code != 200, (
            "Повторное использование уже подтверждённого signature не должно "
            f"давать 200 второй раз! Получено: {second_attempt.text}"
        )
        assert second_attempt.status_code in (400, 401, 403, 404, 410, 422)


class TestVerifyNegative:

    def test_verify_with_stale_reference_code_is_rejected(self, os_authenticated_client):
        """Одноразовый код/signature из исходного лога давно использованы — повтор должен отклоняться."""
        response = os_authenticated_client.verify(
            phone_number=STALE_PHONE, code=STALE_CODE, signature=STALE_SIGNATURE, context="service"
        )
        assert response.status_code != 200
        assert response.status_code in (400, 401, 403, 404, 410, 422), (
            f"Неожиданный статус для устаревшего кода: {response.status_code}: {response.text}"
        )

    @pytest.mark.parametrize("field_to_omit", ["phone_number", "code", "signature", "context"])
    def test_verify_without_required_field(self, os_authenticated_client, field_to_omit):
        response = os_authenticated_client.verify(omit_fields=[field_to_omit])
        assert response.status_code in (400, 422), (
            f"Ожидалась ошибка валидации без '{field_to_omit}', "
            f"получено {response.status_code}: {response.text}"
        )

    def test_verify_with_wrong_code_for_fixed_otp_phone(self, os_auth_client, os_authenticated_client):
        """Даже на номере с фиксированным OTP неверный код (не 56563) должен отклоняться."""
        login_response = os_auth_client.login(phone_number=VERIFY_TEST_PHONE, context="service")
        if login_response.status_code != 200:
            pytest.skip("VERIFY_TEST_PHONE под rate-limit'ом — см. IQUERIX_OS_VERIFY_TEST_PHONE_INDEX")
        signature = login_response.json()["signature"]

        response = os_authenticated_client.verify(
            phone_number=VERIFY_TEST_PHONE, code="00000", signature=signature, context="service"
        )
        assert response.status_code in (400, 401, 403, 422), (
            f"Неверный код должен отклоняться, получено {response.status_code}: {response.text}"
        )

    def test_verify_with_wrong_signature(self, os_authenticated_client):
        response = os_authenticated_client.verify(
            phone_number=VERIFY_TEST_PHONE, code=FIXED_OTP_CODE, signature="0" * 65
        )
        assert response.status_code in (400, 401, 403, 422), (
            f"Неверная подпись должна отклоняться, получено {response.status_code}: {response.text}"
        )

    def test_verify_with_malformed_json_body(self, os_authenticated_client):
        broken_json = '{"phone_number": "998998987882", "code": "56563"'
        response = os_authenticated_client.verify(raw_body=broken_json)
        assert response.status_code in (400, 422), (
            f"Битый JSON должен давать 400/422, получено {response.status_code}"
        )
