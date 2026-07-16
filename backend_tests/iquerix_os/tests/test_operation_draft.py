"""
Тесты POST /s/operation/draft — создание черновика заявки на обслуживание.

Референс из реального лога — ОШИБКА (единственный пример, который у нас есть):
    body: {"vehicle_id": "019dd2ac-0697-7266-9e3a-0e02a9f3ae6b",
           "service_branch_id": "019f6843-6107-709b-8808-16ac801ca423"}
    -> 404 {"success": false, "statusCode": 404, "error": "SERVICE_BRANCH_NOT_FOUND",
            "message": "Филиал сервиса не найден"}

Судя по всему, service_branch_id из лога принадлежал другому контексту/сессии
(другой сервис-аккаунт), поэтому бэкенд не находит филиал для ТЕКУЩЕГО
авторизованного пользователя. Мы используем этот же контракт (404
SERVICE_BRANCH_NOT_FOUND) как подтверждённый негативный сценарий с явно
несуществующим branch_id.

ПОЗИТИВНЫЙ сценарий (создание черновика с РЕАЛЬНО принадлежащим текущему
сервису филиалом + вменяемым vehicle_id) помечен best-effort: у нас нет
подтверждённого примера успешного ответа, а vehicle_id из лога, скорее
всего, принадлежит другому владельцу машины (Iquerix B2B), недоступному
из этой тестовой сессии. Тест admits несколько правдоподобных исходов и
документирует это явно, не пытаясь выдать желаемое за действительное.
"""
import jsonschema
import pytest

from backend_tests.shared.schemas.os_branch_file_operation_schemas import GENERIC_API_ERROR_SCHEMA

pytestmark = [pytest.mark.os, pytest.mark.regression]

# Vehicle из референсного лога — реальный UUID, но, вероятно, принадлежит
# другому владельцу (Iquerix B2B), недоступному текущей тестовой сессии.
REFERENCE_VEHICLE_ID = "019dd2ac-0697-7266-9e3a-0e02a9f3ae6b"
NONEXISTENT_BRANCH_ID = "00000000-0000-0000-0000-000000000000"


class TestOperationDraftConfirmedContract:
    """Сценарии с подтверждённым реальным контрактом ошибки."""

    def test_draft_with_nonexistent_branch_returns_404(self, os_authenticated_client):
        response = os_authenticated_client.create_operation_draft(
            vehicle_id=REFERENCE_VEHICLE_ID, service_branch_id=NONEXISTENT_BRANCH_ID
        )
        assert response.status_code == 404, (
            f"Ожидался 404 SERVICE_BRANCH_NOT_FOUND, получено {response.status_code}: {response.text}"
        )
        body = response.json()
        jsonschema.validate(instance=body, schema=GENERIC_API_ERROR_SCHEMA)
        assert body["error"] == "SERVICE_BRANCH_NOT_FOUND"

    def test_draft_with_malformed_branch_id_does_not_500(self, os_authenticated_client):
        """Не-UUID строка вместо service_branch_id не должна ронять сервер в 500."""
        response = os_authenticated_client.create_operation_draft(
            vehicle_id=REFERENCE_VEHICLE_ID, service_branch_id="not-a-uuid-at-all"
        )
        assert response.status_code < 500, f"Получено {response.status_code}: {response.text}"


@pytest.mark.smoke
class TestOperationDraftWithOwnBranch:
    """
    Best-effort позитивный сценарий: используем РЕАЛЬНО принадлежащий текущей
    сессии филиал (через фикстуру created_branch), но с чужим/недоступным
    vehicle_id из референсного лога. Ожидаем ЛИБО 200 (если backend не
    проверяет владение машиной на этапе draft), ЛИБО осмысленную бизнес-ошибку
    (403/404) — но НЕ 500 и НЕ "филиал не найден" (наш филиал точно существует).
    """

    def test_draft_with_own_branch_and_reference_vehicle(self, os_authenticated_client, created_branch):
        response = os_authenticated_client.create_operation_draft(
            vehicle_id=REFERENCE_VEHICLE_ID, service_branch_id=created_branch["id"]
        )
        assert response.status_code < 500, f"Получено {response.status_code}: {response.text}"

        if response.status_code == 200:
            assert response.json()["success"] is True
        else:
            body = response.json()
            jsonschema.validate(instance=body, schema=GENERIC_API_ERROR_SCHEMA)
            assert body["error"] != "SERVICE_BRANCH_NOT_FOUND", (
                "Наш собственный только что созданный филиал не должен давать "
                f"SERVICE_BRANCH_NOT_FOUND: {response.text}"
            )


class TestOperationDraftMissingFields:

    @pytest.mark.parametrize("field_to_omit", ["vehicle_id", "service_branch_id"])
    def test_draft_without_required_field(self, os_authenticated_client, field_to_omit):
        response = os_authenticated_client.create_operation_draft(
            vehicle_id=REFERENCE_VEHICLE_ID,
            service_branch_id=NONEXISTENT_BRANCH_ID,
            omit_fields=[field_to_omit],
        )
        assert response.status_code in (400, 422), (
            f"Ожидалась ошибка валидации без '{field_to_omit}', "
            f"получено {response.status_code}: {response.text}"
        )

    def test_draft_with_empty_body(self, os_authenticated_client):
        response = os_authenticated_client.create_operation_draft(raw_body={})
        assert response.status_code in (400, 422)


class TestOperationDraftNegativeAuth:

    def test_draft_without_token(self, os_authenticated_client):
        response = os_authenticated_client.create_operation_draft(
            vehicle_id=REFERENCE_VEHICLE_ID, service_branch_id=NONEXISTENT_BRANCH_ID, token=False
        )
        assert response.status_code == 401

    def test_draft_with_invalid_token(self, os_authenticated_client):
        response = os_authenticated_client.create_operation_draft(
            vehicle_id=REFERENCE_VEHICLE_ID, service_branch_id=NONEXISTENT_BRANCH_ID, token="garbage.jwt.value"
        )
        assert response.status_code == 401
