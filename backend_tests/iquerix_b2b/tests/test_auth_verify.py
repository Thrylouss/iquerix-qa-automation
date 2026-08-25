"""
Тесты POST /auth/verify — iQuaRix B2B.

Референс успешного запроса (реальный лог, присланный пользователем):
    body: {"phone_number": "998017892235", "code": "43431",
           "signature": "de6c6766975e5576fce36ea6240df840d2ca1be9ae7f7c7c4e751e64a92d60ef",
           "context": "fleet"}
    -> 200 {"access_token": "...", "refresh_token": "...", "success": true}

VERIFY_TEST_PHONE используется для живого позитивного флоу и для его
целевых негативных сценариев (неверный код/подпись). Каждый живой login
на этом номере ЗАВЕРШАЕТСЯ verify (успешным или намеренно неуспешным) —
подробности состояния лимита после каждого сценария описаны в докстрингах
конкретных тестов (см. api_clients/login_lock_tracker.py).
"""
import jsonschema
import pytest

from backend_tests.iquerix_b2b.conftest import _live_login
from backend_tests.iquerix_b2b.config.test_accounts import B2B_CONTEXT, FIXED_OTP_CODE, VERIFY_TEST_PHONE
from backend_tests.iquerix_b2b.schemas.auth_schemas import VERIFY_SUCCESS_SCHEMA

pytestmark = [pytest.mark.b2b, pytest.mark.regression]

# Реальные, уже использованные (одноразовые) значения из исходного лога —
# годятся только для негативного теста "старая signature больше не работает".
STALE_PHONE = "998017893235"
STALE_CODE = "43431"
STALE_SIGNATURE = "aed3e65f53b753be8ba0d28048e554fb56ab6b5969b454acda26fd1cda4df83c"


@pytest.fixture(scope="module")
def fresh_verify_response(b2b_auth_client, b2b_authenticated_client):
    """
    Живой позитивный флоу: login -> verify на VERIFY_TEST_PHONE.
    Успешный verify СРАЗУ снимает ограничение /auth/login (подтверждённая
    механика) — поэтому следующим тестам в этом файле, которым тоже нужен
    свежий login на этом номере, ждать не придётся.
    """
    login_response = _live_login(b2b_auth_client, VERIFY_TEST_PHONE, "fresh_verify_response")
    if login_response.status_code != 200:
        pytest.skip(
            f"Не удалось получить signature для VERIFY_TEST_PHONE={VERIFY_TEST_PHONE}: "
            f"{login_response.status_code}: {login_response.text}."
        )
    signature = login_response.json()["signature"]

    return b2b_authenticated_client.verify(
        phone_number=VERIFY_TEST_PHONE, code=FIXED_OTP_CODE, signature=signature, context=B2B_CONTEXT
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

    def test_verify_reusing_same_signature_twice_is_rejected(self, b2b_authenticated_client, fresh_verify_response):
        """
        Signature одноразовый: повторное использование уже подтверждённого
        signature должно отклоняться. Этот вызов НЕ успешен (значит, НЕ
        снимает ограничение) — но т.к. login здесь не вызывается заново
        (используем старый signature), состояние лимита не меняется.
        """
        _, used_signature = fresh_verify_response
        second_attempt = b2b_authenticated_client.verify(
            phone_number=VERIFY_TEST_PHONE, code=FIXED_OTP_CODE, signature=used_signature, context=B2B_CONTEXT
        )
        assert second_attempt.status_code != 200, (
            "Повторное использование уже подтверждённого signature не должно "
            f"давать 200 второй раз! Получено: {second_attempt.text}"
        )
        assert second_attempt.status_code in (400, 401, 403, 404, 410, 422)


@pytest.mark.regression
class TestVerifyNegative:

    def test_verify_with_stale_reference_signature_is_rejected(self, b2b_authenticated_client):
        """Одноразовая signature из исходного лога уже использована — повтор должен отклоняться."""
        response = b2b_authenticated_client.verify(
            phone_number=STALE_PHONE, code=STALE_CODE, signature=STALE_SIGNATURE, context=B2B_CONTEXT
        )
        assert response.status_code != 200
        assert response.status_code in (400, 401, 403, 404, 410, 422), (
            f"Неожиданный статус для устаревшей signature: {response.status_code}: {response.text}"
        )

    @pytest.mark.parametrize("field_to_omit", ["phone_number", "code", "signature", "context"])
    def test_verify_without_required_field(self, b2b_authenticated_client, field_to_omit):
        response = b2b_authenticated_client.verify(omit_fields=[field_to_omit])
        assert response.status_code in (400, 422), (
            f"Ожидалась ошибка валидации без '{field_to_omit}', "
            f"получено {response.status_code}: {response.text}"
        )

    def test_verify_with_wrong_code_for_fixed_otp_phone(self, b2b_auth_client, b2b_authenticated_client):
        """
        Даже на номере с фиксированным OTP неверный код (не 43431) должен
        отклоняться — типичная опечатка пользователя при вводе кода.

        ПОСЛЕДНИЙ тест в файле, использующий VERIFY_TEST_PHONE для нового
        login: fresh_verify_response уже завершил цикл успешно (сняв
        ограничение), поэтому этот новый login выполняется свободно. Но
        verify здесь НАМЕРЕННО неуспешен — значит, ограничение снова
        "взводится" на 30 сек. Дальше в файле этот номер больше не
        используется для login, так что это не мешает другим тестам.
        """
        login_response = _live_login(b2b_auth_client, VERIFY_TEST_PHONE, "test_verify_with_wrong_code")
        if login_response.status_code != 200:
            pytest.skip(f"Не удалось получить login для VERIFY_TEST_PHONE: {login_response.text}")
        signature = login_response.json()["signature"]

        response = b2b_authenticated_client.verify(
            phone_number=VERIFY_TEST_PHONE, code="00000", signature=signature, context=B2B_CONTEXT
        )
        assert response.status_code in (400, 401, 403, 422), (
            f"Неверный код должен отклоняться, получено {response.status_code}: {response.text}"
        )

    def test_verify_with_wrong_signature(self, b2b_authenticated_client):
        """Не делает новый login — использует мусорную подпись, состояние лимита не трогает."""
        response = b2b_authenticated_client.verify(
            phone_number=VERIFY_TEST_PHONE, code=FIXED_OTP_CODE, signature="0" * 64, context=B2B_CONTEXT
        )
        assert response.status_code in (400, 401, 403, 422), (
            f"Неверная подпись должна отклоняться, получено {response.status_code}: {response.text}"
        )

    @pytest.mark.security
    def test_verify_with_malformed_json_body(self, b2b_authenticated_client):
        """
        ПОДТВЕРЖДЕНО пользователем живым прогоном: для /auth/verify битый
        JSON — ожидаемое, задокументированное поведение бэкенда вернуть 500
        (в отличие от /auth/login, где 500 на битом JSON помечен как
        подозрение на баг через xfail). Не делает login — не трогает лимит.
        """
        broken_json = '{"phone_number": "998017893235", "code": "43431"'
        response = b2b_authenticated_client.verify(raw_body=broken_json)
        assert response.status_code == 500, (
            f"Ожидался подтверждённый 500, получено {response.status_code}: {response.text}"
        )
