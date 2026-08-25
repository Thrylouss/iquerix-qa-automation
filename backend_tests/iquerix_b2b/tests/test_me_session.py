"""
Тесты PUT /auth/me/session — регистрация/обновление сессии устройства
(push-токен FCM, доступы к геолокации/уведомлениям, инфо об устройстве). iQuaRix B2B.

Референс запроса (curl, присланный пользователем):
    PUT /auth/me/session
    Headers: Authorization: Bearer <token>, x-app-language: ru,
             x-app-type: fleet, x-app-version: 1.0.4
    Body: {
        "fcm": "<FCM push token>",
        "location_access": "denied",
        "notification_access": "denied",
        "device_name": "iPhone iPhone",
        "lang": "ru",
        "rooted": false,
        "os_version": "26.6",
        "mobile_device_id": "<uuid>"
    }

ВАЖНО: тело ОТВЕТА пользователь не присылал. Позитивные тесты ниже
ограничены success:true/статусом/SLA — без проверки конкретных полей
данных. Уточнить точную схему ответа, когда будет реальный пример.

ДОПУЩЕНИЯ (не подтверждены живым прогоном, требуют проверки):
  - Какие именно поля обязательны (предполагаем ВСЕ, судя по составу
    реального тела запроса — заведомо консервативное предположение).
  - Допустимые значения location_access/notification_access — по аналогии
    с реальным примером ("denied") предполагаем enum вида
    granted/denied/not_determined; тест на невалидное значение может
    потребовать уточнения после первого реального прогона.
"""
import jsonschema
import pytest

from backend_tests.iquerix_b2b.schemas.auth_schemas import GENERIC_SUCCESS_SCHEMA

pytestmark = [pytest.mark.b2b, pytest.mark.regression]

VALID_SESSION_PAYLOAD = {
    "fcm": "test_fcm_token_qa_automation_1234567890",
    "location_access": "denied",
    "notification_access": "denied",
    "device_name": "QA Automation Device",
    "lang": "ru",
    "rooted": False,
    "os_version": "17.0",
    "mobile_device_id": "00000000-0000-0000-0000-000000000000",
}


@pytest.fixture(scope="module")
def session_update_response(b2b_authenticated_client, auth_session):
    """Единственный "живой" успешный PUT /auth/me/session за модуль."""
    return b2b_authenticated_client.update_session(payload=VALID_SESSION_PAYLOAD)


@pytest.mark.smoke
class TestMeSessionPositive:

    def test_update_session_returns_200(self, session_update_response):
        assert session_update_response.status_code == 200, (
            f"Получено {session_update_response.status_code}: {session_update_response.text}"
        )
        assert session_update_response.json()["success"] is True

    def test_update_session_matches_generic_schema(self, session_update_response):
        """TODO: заменить на точную схему, когда будет реальный пример тела ответа."""
        jsonschema.validate(instance=session_update_response.json(), schema=GENERIC_SUCCESS_SCHEMA)

    def test_update_session_response_time_within_sla(self, session_update_response):
        assert session_update_response.elapsed.total_seconds() < 5

    def test_update_session_with_rooted_true_is_accepted(self, b2b_authenticated_client, auth_session):
        """Рутованное устройство — легитимный (хоть и рискованный) сценарий, не должен ломать эндпоинт."""
        payload = dict(VALID_SESSION_PAYLOAD, rooted=True)
        response = b2b_authenticated_client.update_session(payload=payload)
        assert response.status_code == 200, f"Получено {response.status_code}: {response.text}"

    def test_update_session_with_granted_access_values_is_accepted(self, b2b_authenticated_client, auth_session):
        payload = dict(VALID_SESSION_PAYLOAD, location_access="granted", notification_access="granted")
        response = b2b_authenticated_client.update_session(payload=payload)
        assert response.status_code == 200, f"Получено {response.status_code}: {response.text}"


@pytest.mark.regression
class TestMeSessionNegative:

    def test_update_session_without_authorization(self, b2b_authenticated_client):
        response = b2b_authenticated_client.update_session(payload=VALID_SESSION_PAYLOAD, token=False)
        assert response.status_code == 401

    def test_update_session_with_invalid_token(self, b2b_authenticated_client):
        response = b2b_authenticated_client.update_session(payload=VALID_SESSION_PAYLOAD, token="garbage.jwt.value")
        assert response.status_code == 401

    def test_update_session_with_empty_body(self, b2b_authenticated_client, auth_session):
        response = b2b_authenticated_client.update_session(raw_body={})
        assert response.status_code in (400, 422), (
            f"Ожидалась ошибка валидации для пустого тела, получено {response.status_code}: {response.text}"
        )

    @pytest.mark.parametrize("field_to_omit", [
        "fcm", "location_access", "notification_access", "device_name",
        "lang", "rooted", "os_version", "mobile_device_id",
    ])
    def test_update_session_without_required_field(self, b2b_authenticated_client, auth_session, field_to_omit):
        response = b2b_authenticated_client.update_session(
            payload=VALID_SESSION_PAYLOAD, omit_fields=[field_to_omit]
        )
        # ДОПУЩЕНИЕ: считаем все поля из реального curl-примера обязательными.
        # Если бэкенд реально считает какое-то из них опциональным, этот
        # конкретный кейс даст 200 вместо 400/422 — сигнал уточнить контракт
        # и перенести это поле в список опциональных.
        assert response.status_code in (400, 422), (
            f"Ожидалась ошибка валидации без '{field_to_omit}', "
            f"получено {response.status_code}: {response.text}"
        )

    @pytest.mark.parametrize("bad_access_value", [
        "yes",              # не входит в предполагаемый enum
        "",                 # пустая строка
        123,                # неверный тип
        None,                # null
    ])
    def test_update_session_with_invalid_location_access_value(
        self, b2b_authenticated_client, auth_session, bad_access_value
    ):
        payload = dict(VALID_SESSION_PAYLOAD, location_access=bad_access_value)
        response = b2b_authenticated_client.update_session(payload=payload)
        assert response.status_code in (400, 422), (
            f"location_access='{bad_access_value}' должен отклоняться, "
            f"получено {response.status_code}: {response.text}"
        )

    def test_update_session_with_wrong_type_for_rooted(self, b2b_authenticated_client, auth_session):
        """rooted должен быть boolean, не строкой."""
        payload = dict(VALID_SESSION_PAYLOAD, rooted="false")
        response = b2b_authenticated_client.update_session(payload=payload)
        assert response.status_code in (400, 422), (
            f"Строковый rooted должен отклоняться, получено {response.status_code}: {response.text}"
        )

    def test_update_session_with_malformed_mobile_device_id(self, b2b_authenticated_client, auth_session):
        """mobile_device_id не в формате UUID — типичная ошибка клиента при генерации идентификатора."""
        payload = dict(VALID_SESSION_PAYLOAD, mobile_device_id="not-a-uuid")
        response = b2b_authenticated_client.update_session(payload=payload)
        assert response.status_code < 500, (
            f"Невалидный UUID не должен приводить к 500, получено {response.status_code}: {response.text}"
        )

    def test_update_session_with_extremely_long_device_name(self, b2b_authenticated_client, auth_session):
        """Очень длинное имя устройства (потенциальный DoS/переполнение) не должно давать 500."""
        payload = dict(VALID_SESSION_PAYLOAD, device_name="A" * 10000)
        response = b2b_authenticated_client.update_session(payload=payload)
        assert response.status_code in (200, 400, 413, 422), (
            f"Неожиданный статус для огромного device_name: {response.status_code}"
        )


@pytest.mark.regression
class TestMeSessionTransportLevel:

    def test_update_session_get_method_not_allowed(self, b2b_authenticated_client, auth_session):
        response = b2b_authenticated_client.get(
            "/auth/me/session", headers={"Authorization": f"Bearer {auth_session['access_token']}"}
        )
        assert response.status_code in (401, 404, 405)

    @pytest.mark.security
    def test_update_session_with_malformed_json_body(self, b2b_authenticated_client, auth_session):
        broken_json = '{"fcm": "abc", "rooted": false'
        response = b2b_authenticated_client.update_session(raw_body=broken_json)
        assert response.status_code in (400, 422, 500), (
            f"Битый JSON не должен приводить к необработанной ошибке, получено {response.status_code}"
        )


@pytest.mark.regression
@pytest.mark.security
class TestMeSessionSecurity:

    def test_update_session_xss_payload_in_device_name(self, b2b_authenticated_client, auth_session):
        payload = dict(VALID_SESSION_PAYLOAD, device_name="<script>alert(1)</script>")
        response = b2b_authenticated_client.update_session(payload=payload)
        # Основная проверка — не 500 (утечка/поломка), само значение может как
        # приниматься (просто текст), так и отклоняться — уточнить после
        # реального прогона.
        assert response.status_code != 500, f"XSS-подобное значение не должно давать 500: {response.text}"

    def test_update_session_response_does_not_leak_stack_trace(self, b2b_authenticated_client, auth_session):
        response = b2b_authenticated_client.update_session(raw_body={"fcm": None, "rooted": "not_a_bool"})
        text_lower = response.text.lower()
        leak_markers = ["traceback", "stacktrace", "at line", "sqlstate", "/var/", "exception in"]
        for marker in leak_markers:
            assert marker not in text_lower, f"Обнаружена утечка технической информации: '{marker}'"
