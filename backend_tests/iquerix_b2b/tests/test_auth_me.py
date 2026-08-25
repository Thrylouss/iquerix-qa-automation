"""
Тесты GET /auth/me — профиль текущего авторизованного пользователя. iQuaRix B2B.

Референс запроса (curl, присланный пользователем):
    GET /auth/me
    Headers: Authorization: Bearer <token>, x-app-language: ru,
             x-app-type: fleet, x-app-version: 1.0.4

ВАЖНО: пользователь прислал только запрос, БЕЗ тела ответа. Позитивные
тесты ниже намеренно ограничены только тем, что можно проверить без
знания точной структуры данных (статус, success:true, заголовки, SLA).
Конкретные поля профиля (id/phone_number/role и т.д.) НЕ проверяются —
как только будет реальный пример тела ответа, стоит:
  1) добавить точную JSON-схему (по образцу ME_SUCCESS_SCHEMA в iquerix_os)
     в schemas/auth_schemas.py;
  2) дописать sanity-check на конкретные поля (например, что phone_number
     соответствует AUTH_SESSION_PHONE), как это сделано в
     iquerix_os/tests/test_auth_me.py.
"""
import pytest

from backend_tests.iquerix_b2b.schemas.auth_schemas import GENERIC_SUCCESS_SCHEMA
import jsonschema

pytestmark = [pytest.mark.b2b, pytest.mark.regression]


@pytest.mark.smoke
class TestMePositive:

    def test_me_returns_200_and_success_true(self, me_response):
        assert me_response.status_code == 200
        assert me_response.json()["success"] is True

    def test_me_response_matches_generic_schema(self, me_response):
        """TODO: заменить на точную схему, когда будет реальный пример тела ответа."""
        jsonschema.validate(instance=me_response.json(), schema=GENERIC_SUCCESS_SCHEMA)

    def test_me_response_headers(self, me_response):
        content_type = me_response.headers.get("content-type", "")
        assert "application/json" in content_type

    def test_me_response_time_within_sla(self, me_response):
        assert me_response.elapsed.total_seconds() < 5


@pytest.mark.regression
class TestMeNegative:

    def test_me_without_authorization_header(self, b2b_authenticated_client, auth_session):
        response = b2b_authenticated_client.me(token=False)
        assert response.status_code == 401, (
            f"Запрос без Authorization должен давать 401, получено {response.status_code}: {response.text}"
        )

    def test_me_with_invalid_token(self, b2b_authenticated_client, auth_session):
        response = b2b_authenticated_client.me(token="this.is.not-a-valid-jwt")
        assert response.status_code == 401, (
            f"Невалидный токен должен давать 401, получено {response.status_code}: {response.text}"
        )

    def test_me_with_empty_bearer_token(self, b2b_authenticated_client, auth_session):
        response = b2b_authenticated_client.me(extra_headers={"Authorization": "Bearer "})
        assert response.status_code == 401

    def test_me_with_wrong_auth_scheme(self, b2b_authenticated_client, auth_session):
        """Схема должна быть именно Bearer, не Basic/Token/пусто."""
        response = b2b_authenticated_client.me(extra_headers={"Authorization": "Token abc123"})
        assert response.status_code == 401

    def test_me_with_access_token_from_different_login_cycle_still_works_or_401(
        self, b2b_authenticated_client, auth_session
    ):
        """
        Явно битый, но структурно похожий на JWT токен (3 сегмента, base64-мусор)
        не должен приводить к 500 — только к штатной ошибке авторизации.
        """
        response = b2b_authenticated_client.me(token="aGVsbG8.d29ybGQ.ZmFrZQ")
        assert response.status_code in (401, 403), (
            f"Ожидался 401/403 для структурно похожего, но невалидного токена, "
            f"получено {response.status_code}: {response.text}"
        )
        assert response.status_code != 500


@pytest.mark.regression
class TestMeTransportLevel:

    def test_me_post_method_not_allowed(self, b2b_authenticated_client, auth_session):
        """Эндпоинт задокументирован как GET."""
        response = b2b_authenticated_client.post(
            "/auth/me", headers={"Authorization": f"Bearer {auth_session['access_token']}"}
        )
        assert response.status_code in (401, 404, 405)
