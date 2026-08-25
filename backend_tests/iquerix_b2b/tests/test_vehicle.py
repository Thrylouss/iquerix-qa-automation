"""
Тесты GET /f/vehicle/{vehicle_id} — информация о транспортном средстве. iQuaRix B2B.

Референс запроса (curl, присланный пользователем):
    GET /f/vehicle/01a018de-9d5e-71ae-9a8b-278950144411
    Headers: Authorization: Bearer <token>, x-app-language: ru,
             x-app-type: fleet, x-app-version: 1.0.4

ВАЖНО: тело ответа пользователь не присылал. Позитивные тесты, использующие
этот vehicle_id, ПОМЕЧЕНЫ как требующие подтверждения — является ли это ТС
выделенным QA-объектом или реальным ТС из боевого флита.
"""
import jsonschema
import pytest

from backend_tests.iquerix_b2b.schemas.auth_schemas import GENERIC_SUCCESS_SCHEMA

pytestmark = [pytest.mark.b2b, pytest.mark.regression]

# ДОПУЩЕНИЕ: взят из реального curl-примера пользователя — требует
# подтверждения, тестовое это ТС или боевое.
REFERENCE_VEHICLE_ID = "01a018de-9d5e-71ae-9a8b-278950144411"

# Синтаксически валидный UUID, точно не существующий в системе.
NONEXISTENT_VEHICLE_ID = "00000000-0000-0000-0000-000000000000"


@pytest.mark.smoke
class TestVehiclePositive:

    def test_vehicle_returns_200_for_reference_id(self, b2b_authenticated_client, me_response):
        """ТРЕБУЕТ ПОДТВЕРЖДЕНИЯ: см. докстринг файла про REFERENCE_VEHICLE_ID."""
        response = b2b_authenticated_client.get_vehicle(vehicle_id=REFERENCE_VEHICLE_ID)
        assert response.status_code == 200, f"Получено {response.status_code}: {response.text}"
        assert response.json()["success"] is True

    def test_vehicle_response_matches_generic_schema(self, b2b_authenticated_client, me_response):
        """TODO: заменить на точную схему, когда будет реальный пример тела ответа."""
        response = b2b_authenticated_client.get_vehicle(vehicle_id=REFERENCE_VEHICLE_ID)
        jsonschema.validate(instance=response.json(), schema=GENERIC_SUCCESS_SCHEMA)

    def test_vehicle_response_time_within_sla(self, b2b_authenticated_client, me_response):
        response = b2b_authenticated_client.get_vehicle(vehicle_id=REFERENCE_VEHICLE_ID)
        assert response.elapsed.total_seconds() < 5


@pytest.mark.regression
class TestVehicleNegative:

    def test_vehicle_without_token(self, b2b_authenticated_client):
        response = b2b_authenticated_client.get_vehicle(vehicle_id=NONEXISTENT_VEHICLE_ID, token=False)
        assert response.status_code == 401

    def test_vehicle_with_invalid_token(self, b2b_authenticated_client):
        response = b2b_authenticated_client.get_vehicle(vehicle_id=NONEXISTENT_VEHICLE_ID, token="garbage.jwt.value")
        assert response.status_code == 401

    def test_vehicle_with_nonexistent_id(self, b2b_authenticated_client, me_response):
        response = b2b_authenticated_client.get_vehicle(vehicle_id=NONEXISTENT_VEHICLE_ID)
        assert response.status_code in (400, 403, 404), (
            f"Несуществующий vehicle_id должен давать 400/403/404, получено {response.status_code}: {response.text}"
        )
        assert response.status_code != 500

    @pytest.mark.parametrize("bad_id", [
        "not-a-uuid",
        "123",
        "",
        "'; DROP TABLE vehicles;--",
    ])
    def test_vehicle_with_malformed_id(self, b2b_authenticated_client, me_response, bad_id):
        response = b2b_authenticated_client.get_vehicle(vehicle_id=bad_id)
        assert response.status_code != 500, (
            f"vehicle_id='{bad_id}' не должен приводить к 500: {response.text[:200]}"
        )

    def test_vehicle_belonging_to_another_context_returns_403_or_404(self, b2b_authenticated_client, me_response):
        """
        Синтаксически валидный, но заведомо чужой UUID — проверка на IDOR
        (Insecure Direct Object Reference): доступ к чужому ТС не должен
        давать 200 с чужими данными.
        """
        foreign_looking_id = "ffffffff-ffff-ffff-ffff-ffffffffffff"
        response = b2b_authenticated_client.get_vehicle(vehicle_id=foreign_looking_id)
        assert response.status_code != 200, (
            "Доступ к, вероятно, несуществующему/чужому ТС не должен давать 200"
        )


@pytest.mark.regression
class TestVehicleTransportLevel:

    def test_vehicle_post_method_not_allowed(self, b2b_authenticated_client, auth_session):
        response = b2b_authenticated_client.post(
            f"/f/vehicle/{NONEXISTENT_VEHICLE_ID}",
            headers={"Authorization": f"Bearer {auth_session['access_token']}"},
        )
        assert response.status_code in (401, 404, 405)
