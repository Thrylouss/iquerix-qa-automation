"""
Тесты GET /auth/me — профиль текущего авторизованного пользователя.

Референс успешного ответа (реальный лог): success=true, data содержит
id/phone_number/status/branch_id/role/service и т.д.
"""
import jsonschema
import pytest

from backend_tests.shared.schemas.os_authenticated_schemas import ME_SUCCESS_SCHEMA

pytestmark = [pytest.mark.os, pytest.mark.regression]


@pytest.mark.smoke
class TestMePositive:

    def test_me_returns_200_and_success_true(self, me_response):
        assert me_response.status_code == 200
        assert me_response.json()["success"] is True

    def test_me_response_matches_schema(self, me_response):
        jsonschema.validate(instance=me_response.json(), schema=ME_SUCCESS_SCHEMA)

    def test_me_returns_expected_test_user(self, me_response):
        """Санити-чек: токен принадлежит ожидаемому тестовому пользователю сервиса."""
        data = me_response.json()["data"]
        assert data["phone_number"] == "998998987882"
        assert data["status"] == "active"
        assert data["role"]["type"] == "service"

    def test_me_response_time_within_sla(self, me_response):
        assert me_response.elapsed.total_seconds() < 5


class TestMeNegative:

    def test_me_without_authorization_header(self, os_authenticated_client):
        response = os_authenticated_client.me(token=False)
        assert response.status_code == 401, (
            f"Запрос без Authorization должен давать 401, получено {response.status_code}: {response.text}"
        )

    def test_me_with_invalid_token(self, os_authenticated_client):
        response = os_authenticated_client.me(token="this.is.not-a-valid-jwt")
        assert response.status_code == 401, (
            f"Невалидный токен должен давать 401, получено {response.status_code}: {response.text}"
        )

    def test_me_with_empty_bearer_token(self, os_authenticated_client):
        response = os_authenticated_client.me(extra_headers={"Authorization": "Bearer "})
        assert response.status_code == 401

    def test_me_with_wrong_auth_scheme(self, os_authenticated_client):
        """Схема должна быть именно Bearer, не Basic/Token/пусто."""
        response = os_authenticated_client.me(extra_headers={"Authorization": "Token abc123"})
        assert response.status_code == 401
