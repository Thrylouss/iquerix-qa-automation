"""
Тесты GET /s/operation/ — список заявок/операций сервиса с фильтром по статусам.

Референс успешных запросов (реальные логи):
    ?statuses=draft&statuses=start_approved_by_customer&statuses=in_progress&page=1
    ?statuses=completed&statuses=completion_approved_by_customer&page=1
    -> 200 {"success": true, "data": {"service_operations": [], "in_progress_count": 0,
            "cancelled_count": 0, "completed_count": 0, "page": 1, "total_pages": 0}}
"""
import jsonschema
import pytest

from backend_tests.shared.schemas.os_authenticated_schemas import OPERATIONS_LIST_SCHEMA

pytestmark = [pytest.mark.os, pytest.mark.regression]

IN_PROGRESS_STATUSES = ["draft", "start_approved_by_customer", "in_progress"]
COMPLETED_STATUSES = ["completed", "completion_approved_by_customer"]


@pytest.mark.smoke
class TestOperationsListPositive:

    @pytest.mark.parametrize("statuses", [IN_PROGRESS_STATUSES, COMPLETED_STATUSES], ids=["in_progress", "completed"])
    def test_operations_list_with_valid_statuses(self, os_authenticated_client, me_response, statuses):
        response = os_authenticated_client.operations(statuses=statuses, page=1)
        assert response.status_code == 200, f"Получено {response.status_code}: {response.text}"
        assert response.json()["success"] is True

    def test_operations_list_matches_schema(self, os_authenticated_client, me_response):
        response = os_authenticated_client.operations(statuses=IN_PROGRESS_STATUSES, page=1)
        jsonschema.validate(instance=response.json(), schema=OPERATIONS_LIST_SCHEMA)

    def test_operations_list_page_field_matches_requested_page(self, os_authenticated_client, me_response):
        response = os_authenticated_client.operations(statuses=IN_PROGRESS_STATUSES, page=1)
        assert response.json()["data"]["page"] == 1

    def test_operations_list_without_statuses_filter(self, os_authenticated_client, me_response):
        """Без фильтра по статусам эндпоинт не должен падать (возвращает либо всё, либо требует статус)."""
        response = os_authenticated_client.operations(statuses=[], page=1)
        assert response.status_code < 500, f"Получено {response.status_code}: {response.text}"


class TestOperationsListNegative:

    def test_operations_list_without_token(self, os_authenticated_client):
        response = os_authenticated_client.operations(statuses=IN_PROGRESS_STATUSES, token=False)
        assert response.status_code == 401

    def test_operations_list_with_unknown_status_value(self, os_authenticated_client, me_response):
        """Несуществующий статус — не должен приводить к 500."""
        response = os_authenticated_client.operations(statuses=["totally_made_up_status"], page=1)
        assert response.status_code < 500, f"Получено {response.status_code}: {response.text}"

    @pytest.mark.parametrize("bad_page", [0, -1, "abc"])
    def test_operations_list_with_invalid_page(self, os_authenticated_client, me_response, bad_page):
        response = os_authenticated_client.operations(
            raw_params={"statuses": IN_PROGRESS_STATUSES, "page": bad_page}
        )
        assert response.status_code < 500, (
            f"Некорректный page='{bad_page}' не должен ронять сервер, получено {response.status_code}: {response.text}"
        )
