"""
Тесты GET /notification/ — список уведомлений пользователя (с пагинацией). iQuaRix B2B.

Референс запроса (curl, присланный пользователем):
    GET /notification/?page=1&limit=10
    Headers: Authorization: Bearer <token>, x-app-language: ru,
             x-app-type: fleet, x-app-version: 1.0.4

ВАЖНО: тело ответа пользователь не присылал. Позитивные тесты ниже
ограничены success:true/статусом/SLA. Как только будет реальный пример
ответа — добавить точную схему (структура пагинации: data как массив
напрямую, как в iquerix_os, или обёрнута в {items, page, total_pages}?
сейчас неизвестно) и sanity-проверки на поля элементов списка.
"""
import jsonschema
import pytest

from backend_tests.iquerix_b2b.schemas.auth_schemas import GENERIC_SUCCESS_SCHEMA

pytestmark = [pytest.mark.b2b, pytest.mark.regression]


@pytest.mark.smoke
class TestNotificationsPositive:

    def test_notifications_returns_200(self, b2b_authenticated_client, me_response):
        response = b2b_authenticated_client.notifications(page=1, limit=10)
        assert response.status_code == 200, f"Получено {response.status_code}: {response.text}"
        assert response.json()["success"] is True

    def test_notifications_matches_generic_schema(self, b2b_authenticated_client, me_response):
        """TODO: заменить на точную схему, когда будет реальный пример тела ответа."""
        response = b2b_authenticated_client.notifications(page=1, limit=10)
        jsonschema.validate(instance=response.json(), schema=GENERIC_SUCCESS_SCHEMA)

    def test_notifications_response_time_within_sla(self, b2b_authenticated_client, me_response):
        response = b2b_authenticated_client.notifications(page=1, limit=10)
        assert response.elapsed.total_seconds() < 5

    def test_notifications_with_different_limit_is_accepted(self, b2b_authenticated_client, me_response):
        response = b2b_authenticated_client.notifications(page=1, limit=50)
        assert response.status_code == 200, f"Получено {response.status_code}: {response.text}"


@pytest.mark.regression
class TestNotificationsNegative:

    def test_notifications_without_token(self, b2b_authenticated_client):
        response = b2b_authenticated_client.notifications(token=False)
        assert response.status_code == 401

    def test_notifications_with_invalid_token(self, b2b_authenticated_client):
        response = b2b_authenticated_client.notifications(token="garbage.jwt.value")
        assert response.status_code == 401

    @pytest.mark.parametrize("bad_page", ["-1", "0", "abc", "999999999999999999"])
    def test_notifications_with_invalid_page(self, b2b_authenticated_client, me_response, bad_page):
        """
        Невалидная страница не должна давать 500. ДОПУЩЕНИЕ: конкретно
        page=0/отрицательные могут как отклоняться (400/422), так и
        трактоваться как page=1 (200) — оба варианта приемлемы, лишь бы
        не было 500.
        """
        response = b2b_authenticated_client.notifications(raw_params={"page": bad_page, "limit": 10})
        assert response.status_code != 500, (
            f"Невалидный page='{bad_page}' не должен приводить к 500: {response.text}"
        )

    @pytest.mark.parametrize("bad_limit", ["-1", "0", "abc"])
    def test_notifications_with_invalid_limit(self, b2b_authenticated_client, me_response, bad_limit):
        response = b2b_authenticated_client.notifications(raw_params={"page": 1, "limit": bad_limit})
        assert response.status_code != 500, (
            f"Невалидный limit='{bad_limit}' не должен приводить к 500: {response.text}"
        )

    def test_notifications_with_excessively_large_limit_is_bounded_or_rejected(
        self, b2b_authenticated_client, me_response
    ):
        """Очень большой limit (потенциальная DoS-нагрузка на БД) должен либо отклоняться, либо ограничиваться сервером."""
        response = b2b_authenticated_client.notifications(page=1, limit=1000000)
        assert response.status_code != 500, f"Огромный limit не должен приводить к 500: {response.text}"

    def test_notifications_without_query_params_uses_defaults(self, b2b_authenticated_client, me_response):
        """Запрос совсем без page/limit не должен ломаться — вероятно, есть значения по умолчанию."""
        response = b2b_authenticated_client.notifications(raw_params={})
        assert response.status_code < 500, f"Получено {response.status_code}: {response.text}"


@pytest.mark.regression
class TestNotificationsTransportLevel:

    def test_notifications_post_method_not_allowed(self, b2b_authenticated_client, auth_session):
        response = b2b_authenticated_client.post(
            "/notification/", headers={"Authorization": f"Bearer {auth_session['access_token']}"}
        )
        assert response.status_code in (401, 404, 405)
