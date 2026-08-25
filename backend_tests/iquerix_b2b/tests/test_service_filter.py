"""
Тесты GET /service/filter — фильтры/справочник сервисов. iQuaRix B2B.

Референс запроса (curl, присланный пользователем):
    GET /service/filter
    Headers: Authorization: Bearer <token>, x-app-language: ru,
             x-app-type: fleet, x-app-version: 1.0.4

ВАЖНО: тело ответа пользователь не присылал, а сам смысл эндпоинта
("фильтр") предполагает наличие query-параметров, которых мы тоже не
знаем. Позитивные тесты ниже ограничены самым базовым уровнем
(success:true/статус/SLA) без query-параметров вообще. Как только будет
реальный пример ответа и/или список поддерживаемых параметров фильтрации —
дополнить точной схемой и тестами на конкретные фильтры.
"""
import jsonschema
import pytest

from backend_tests.iquerix_b2b.schemas.auth_schemas import GENERIC_SUCCESS_SCHEMA

pytestmark = [pytest.mark.b2b, pytest.mark.regression]


@pytest.mark.smoke
class TestServiceFilterPositive:

    def test_service_filter_returns_200(self, b2b_authenticated_client, me_response):
        response = b2b_authenticated_client.service_filter()
        assert response.status_code == 200, f"Получено {response.status_code}: {response.text}"
        assert response.json()["success"] is True

    def test_service_filter_matches_generic_schema(self, b2b_authenticated_client, me_response):
        """TODO: заменить на точную схему, когда будет реальный пример тела ответа."""
        response = b2b_authenticated_client.service_filter()
        jsonschema.validate(instance=response.json(), schema=GENERIC_SUCCESS_SCHEMA)

    def test_service_filter_response_time_within_sla(self, b2b_authenticated_client, me_response):
        response = b2b_authenticated_client.service_filter()
        assert response.elapsed.total_seconds() < 5


@pytest.mark.regression
class TestServiceFilterNegative:

    def test_service_filter_without_token(self, b2b_authenticated_client):
        response = b2b_authenticated_client.service_filter(token=False)
        assert response.status_code == 401

    def test_service_filter_with_invalid_token(self, b2b_authenticated_client):
        response = b2b_authenticated_client.service_filter(token="garbage.jwt.value")
        assert response.status_code == 401

    def test_service_filter_with_unexpected_query_param(self, b2b_authenticated_client, me_response):
        """Лишний неизвестный query-параметр не должен ломать эндпоинт."""
        response = b2b_authenticated_client.service_filter(params={"unexpected_param": "hacker_value"})
        assert response.status_code < 500


@pytest.mark.regression
class TestServiceFilterTransportLevel:

    def test_service_filter_post_method_not_allowed(self, b2b_authenticated_client, auth_session):
        response = b2b_authenticated_client.post(
            "/service/filter", headers={"Authorization": f"Bearer {auth_session['access_token']}"}
        )
        assert response.status_code in (401, 404, 405)
