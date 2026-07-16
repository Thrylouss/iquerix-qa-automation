"""
Тесты POST/GET /s/branch — создание и список филиалов сервиса.

Референсы из реальных логов:
  POST успешный: полная структура (name, service_types, primary_service_type_id,
                 lat/long, phone_number, schedule, address, images) -> 200 {"data": {"id": "..."}}
  POST ошибка 400: phone_number "998987882" (9 цифр вместо 12) ->
      {"success": false, "statusCode": 400, "error": "BAD_REQUEST",
       "message": "body/phone_number Format must be exactly 998XXXXXXXXX (12 digits total)"}
  GET успешный: список филиалов с вложенными primary_service_type/images.
"""
import jsonschema
import pytest

from backend_tests.shared.config.branch_reference_payload import get_reference_branch_payload
from backend_tests.shared.schemas.os_branch_file_operation_schemas import (
    BRANCH_CREATE_SUCCESS_SCHEMA,
    BRANCH_LIST_SCHEMA,
    GENERIC_API_ERROR_SCHEMA,
)

pytestmark = [pytest.mark.os, pytest.mark.regression]


@pytest.mark.smoke
class TestBranchCreatePositive:

    def test_create_branch_returns_200(self, created_branch):
        assert isinstance(created_branch["id"], str) and len(created_branch["id"]) > 0

    def test_create_branch_matches_schema(self, os_authenticated_client, uploaded_service_image):
        """Отдельный вызов (не через кешированную фикстуру) — специально для проверки самой схемы ответа."""
        payload = get_reference_branch_payload()
        payload["images"] = [{"file_id": uploaded_service_image["id"], "sort_order": 0}]
        response = os_authenticated_client.create_branch(payload=payload)
        assert response.status_code == 200, f"Получено {response.status_code}: {response.text}"
        jsonschema.validate(instance=response.json(), schema=BRANCH_CREATE_SUCCESS_SCHEMA)


@pytest.mark.smoke
class TestBranchListPositive:

    def test_list_branches_returns_200(self, os_authenticated_client, auth_session):
        response = os_authenticated_client.list_branches()
        assert response.status_code == 200, f"Получено {response.status_code}: {response.text}"
        assert response.json()["success"] is True

    def test_list_branches_matches_schema(self, os_authenticated_client, auth_session):
        response = os_authenticated_client.list_branches()
        jsonschema.validate(instance=response.json(), schema=BRANCH_LIST_SCHEMA)

    def test_list_branches_contains_created_branch(self, os_authenticated_client, created_branch):
        """Санити-чек: только что созданный филиал должен появиться в списке."""
        branches = os_authenticated_client.list_branches().json()["data"]
        branch_ids = [b["id"] for b in branches]
        assert created_branch["id"] in branch_ids, (
            f"Созданный филиал {created_branch['id']} не найден в списке /s/branch"
        )


class TestBranchCreateNegative:

    def test_create_branch_without_token(self, os_authenticated_client):
        payload = get_reference_branch_payload()
        response = os_authenticated_client.create_branch(payload=payload, token=False)
        assert response.status_code == 401

    @pytest.mark.parametrize("bad_phone", [
        "998987882",       # 9 цифр — подтверждено реальным 400 в логе
        "99899898788299",  # слишком длинный
        "9989989878",      # слишком короткий
        "abc998987882",    # буквы
    ])
    def test_create_branch_with_invalid_phone_format(self, os_authenticated_client, bad_phone):
        payload = get_reference_branch_payload()
        payload["phone_number"] = bad_phone
        response = os_authenticated_client.create_branch(payload=payload)

        assert response.status_code == 400, (
            f"Невалидный формат номера '{bad_phone}' должен давать 400, "
            f"получено {response.status_code}: {response.text}"
        )
        body = response.json()
        jsonschema.validate(instance=body, schema=GENERIC_API_ERROR_SCHEMA)
        assert body["error"] == "BAD_REQUEST"
        assert "phone_number" in body["message"]

    @pytest.mark.parametrize("field_to_omit", ["name", "primary_service_type_id", "lat", "long", "phone_number"])
    def test_create_branch_without_required_field(self, os_authenticated_client, field_to_omit):
        payload = get_reference_branch_payload()
        payload.pop(field_to_omit, None)
        response = os_authenticated_client.create_branch(payload=payload)
        assert response.status_code in (400, 422), (
            f"Ожидалась ошибка валидации без '{field_to_omit}', "
            f"получено {response.status_code}: {response.text}"
        )

    @pytest.mark.parametrize("bad_lat,bad_long", [(999, 69.29), (41.34, 999), (-999, -999)])
    def test_create_branch_with_out_of_range_coordinates(self, os_authenticated_client, bad_lat, bad_long):
        payload = get_reference_branch_payload()
        payload["lat"] = bad_lat
        payload["long"] = bad_long
        response = os_authenticated_client.create_branch(payload=payload)
        assert response.status_code < 500, (
            f"Координаты вне диапазона не должны ронять сервер, получено {response.status_code}: {response.text}"
        )

    def test_create_branch_with_nonexistent_service_type_id(self, os_authenticated_client):
        payload = get_reference_branch_payload()
        payload["primary_service_type_id"] = "00000000-0000-0000-0000-000000000000"
        response = os_authenticated_client.create_branch(payload=payload)
        assert response.status_code < 500, f"Получено {response.status_code}: {response.text}"


class TestBranchListNegative:

    def test_list_branches_without_token(self, os_authenticated_client):
        response = os_authenticated_client.list_branches(token=False)
        assert response.status_code == 401

    def test_list_branches_with_invalid_token(self, os_authenticated_client):
        response = os_authenticated_client.list_branches(token="garbage.jwt.value")
        assert response.status_code == 401
