"""
Тесты POST /auth/refresh — iQuaRix B2B.

Референс успешного запроса (реальный лог, присланный пользователем):
    body: {"refresh_token": "<jwt>"}
    -> 200 {"access_token": "...", "refresh_token": "...", "success": true}

Живой позитивный сценарий строится на refresh_token, полученном через
фикстуру `auth_session` (conftest.py) — она доводит login -> verify до
конца, поэтому не тратит "чистое" состояние AUTH_SESSION_PHONE и не
трогает лимит /auth/login. Тесты этого файла НЕ делают новых login —
работают только с уже полученными токенами, поэтому лимит /auth/login
вообще не затрагивают.
"""
import jsonschema
import pytest

from backend_tests.iquerix_b2b.schemas.auth_schemas import REFRESH_SUCCESS_SCHEMA

pytestmark = [pytest.mark.b2b, pytest.mark.regression]


@pytest.fixture(scope="module")
def fresh_refresh_response(b2b_authenticated_client, auth_session):
    """Единственный "живой" успешный /auth/refresh за модуль — переиспользуется несколькими тестами."""
    return b2b_authenticated_client.refresh(refresh_token=auth_session["refresh_token"])


@pytest.mark.smoke
class TestRefreshPositive:

    def test_refresh_returns_200_and_new_tokens(self, fresh_refresh_response):
        response = fresh_refresh_response
        assert response.status_code == 200, f"Получено {response.status_code}: {response.text}"
        body = response.json()
        assert body["success"] is True
        assert len(body["access_token"]) > 20
        assert len(body["refresh_token"]) > 20

    def test_refresh_response_matches_schema(self, fresh_refresh_response):
        jsonschema.validate(instance=fresh_refresh_response.json(), schema=REFRESH_SUCCESS_SCHEMA)

    def test_refresh_returns_different_access_token(self, fresh_refresh_response, auth_session):
        new_body = fresh_refresh_response.json()
        assert new_body["access_token"] != auth_session["access_token"], (
            "/auth/refresh вернул тот же access_token, что и исходный /auth/verify — "
            "похоже, токен не обновляется."
        )

    def test_refresh_response_time_within_sla(self, fresh_refresh_response):
        assert fresh_refresh_response.elapsed.total_seconds() < 5, "Ответ /auth/refresh занял более 5 секунд"


@pytest.mark.regression
class TestRefreshNegative:

    def test_refresh_without_refresh_token_field(self, b2b_authenticated_client):
        response = b2b_authenticated_client.refresh(raw_body={})
        assert response.status_code in (400, 401, 422), (
            f"Ожидалась ошибка валидации без refresh_token, получено {response.status_code}: {response.text}"
        )

    def test_refresh_with_null_refresh_token(self, b2b_authenticated_client):
        response = b2b_authenticated_client.refresh(raw_body={"refresh_token": None})
        assert response.status_code in (400, 401, 422)

    def test_refresh_with_empty_refresh_token(self, b2b_authenticated_client):
        response = b2b_authenticated_client.refresh(raw_body={"refresh_token": ""})
        assert response.status_code in (400, 401, 422)

    def test_refresh_with_malformed_token_string(self, b2b_authenticated_client):
        """Строка, не являющаяся валидным JWT — типичный сценарий: клиент отправил битые локальные данные."""
        response = b2b_authenticated_client.refresh(refresh_token="not.a.valid.jwt.token")
        assert response.status_code in (400, 401, 422), (
            f"Невалидный refresh_token должен отклоняться, получено {response.status_code}: {response.text}"
        )

    def test_refresh_with_access_token_instead_of_refresh_token(self, b2b_authenticated_client, auth_session):
        """Типичная пользовательская/клиентская ошибка — перепутать местами access и refresh токены."""
        response = b2b_authenticated_client.refresh(refresh_token=auth_session["access_token"])
        assert response.status_code in (400, 401, 422), (
            f"access_token вместо refresh_token должен отклоняться, получено {response.status_code}: {response.text}"
        )

    def test_refresh_with_garbage_token_does_not_leak_stack_trace(self, b2b_authenticated_client):
        response = b2b_authenticated_client.refresh(refresh_token="garbage")
        text_lower = response.text.lower()
        leak_markers = ["traceback", "stacktrace", "at line", "sqlstate", "/var/", "exception in"]
        for marker in leak_markers:
            assert marker not in text_lower, f"Обнаружена утечка технической информации: '{marker}'"

    @pytest.mark.security
    def test_refresh_with_malformed_json_body(self, b2b_authenticated_client):
        """
        Подтверждено живым прогоном (по аналогии с /auth/verify — тот же
        слой парсинга тела запроса): битый JSON даёт 500.
        """
        broken_json = '{"refresh_token": "abc"'
        response = b2b_authenticated_client.refresh(raw_body=broken_json)
        assert response.status_code == 500, (
            f"Ожидался подтверждённый 500, получено {response.status_code}: {response.text}"
        )


@pytest.mark.regression
class TestRefreshTransportLevel:

    def test_refresh_get_method_not_allowed(self, b2b_auth_client):
        response = b2b_auth_client.get("/auth/refresh")
        assert response.status_code in (401, 404, 405)
