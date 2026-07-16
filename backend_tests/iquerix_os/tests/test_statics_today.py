"""
Тесты GET /s/statics/today — дашборд-статистика сервиса за сегодняшний день.

Референс успешного ответа (реальный лог):
    {"success": true, "data": {"revenue": {"today": 0, "percent_change": 0},
     "service_count": {"today": 0, "percent_change": 0}, "last_operation": null}}
"""
import jsonschema
import pytest

from backend_tests.shared.schemas.os_authenticated_schemas import STATICS_TODAY_SCHEMA

pytestmark = [pytest.mark.os, pytest.mark.regression]


@pytest.mark.smoke
class TestStaticsTodayPositive:

    def test_statics_today_returns_200(self, os_authenticated_client, me_response):
        response = os_authenticated_client.statics_today()
        assert response.status_code == 200, f"Получено {response.status_code}: {response.text}"
        assert response.json()["success"] is True

    def test_statics_today_matches_schema(self, os_authenticated_client, me_response):
        response = os_authenticated_client.statics_today()
        jsonschema.validate(instance=response.json(), schema=STATICS_TODAY_SCHEMA)

    def test_statics_today_numeric_fields_are_not_negative(self, os_authenticated_client, me_response):
        """Базовая проверка бизнес-логики: выручка и количество за день не должны быть отрицательными."""
        data = os_authenticated_client.statics_today().json()["data"]
        assert data["revenue"]["today"] >= 0
        assert data["service_count"]["today"] >= 0


class TestStaticsTodayNegative:

    def test_statics_today_without_token(self, os_authenticated_client):
        response = os_authenticated_client.statics_today(token=False)
        assert response.status_code == 401

    def test_statics_today_with_invalid_token(self, os_authenticated_client):
        response = os_authenticated_client.statics_today(token="invalid.jwt.token")
        assert response.status_code == 401
