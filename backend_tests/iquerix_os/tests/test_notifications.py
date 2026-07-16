"""
Тесты GET /notification/ — список уведомлений текущего пользователя.

Референс успешного ответа (реальный лог): success=true, data — массив
объектов с id/title/body/sender_type/created_at/context_type/read.
"""
import jsonschema
import pytest

from backend_tests.shared.schemas.os_authenticated_schemas import NOTIFICATIONS_LIST_SCHEMA

pytestmark = [pytest.mark.os, pytest.mark.regression]


@pytest.mark.smoke
class TestNotificationsPositive:

    def test_notifications_returns_200(self, os_authenticated_client, me_response):
        response = os_authenticated_client.notifications()
        assert response.status_code == 200, f"Получено {response.status_code}: {response.text}"
        assert response.json()["success"] is True

    def test_notifications_matches_schema(self, os_authenticated_client, me_response):
        response = os_authenticated_client.notifications()
        jsonschema.validate(instance=response.json(), schema=NOTIFICATIONS_LIST_SCHEMA)

    def test_notifications_items_have_consistent_read_flag_type(self, os_authenticated_client, me_response):
        data = os_authenticated_client.notifications().json()["data"]
        for item in data:
            assert isinstance(item["read"], bool), f"Поле 'read' должно быть boolean: {item}"

    def test_notifications_sorted_by_created_at_desc(self, os_authenticated_client, me_response):
        """Судя по логу, уведомления приходят от новых к старым — проверяем сортировку."""
        data = os_authenticated_client.notifications().json()["data"]
        created_dates = [item["created_at"] for item in data]
        assert created_dates == sorted(created_dates, reverse=True), (
            "Уведомления должны быть отсортированы по created_at по убыванию (новые сверху)"
        )


class TestNotificationsNegative:

    def test_notifications_without_token(self, os_authenticated_client):
        response = os_authenticated_client.notifications(token=False)
        assert response.status_code == 401

    def test_notifications_with_invalid_token(self, os_authenticated_client):
        response = os_authenticated_client.notifications(token="garbage.jwt.value")
        assert response.status_code == 401
