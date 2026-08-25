"""
Тесты GET /qr/{code} — распознавание QR-кода транспортного средства. iQuaRix B2B.

Референс запроса (curl, присланный пользователем):
    GET /qr/06FX40ZKENTAZ7VHKQS4916T3R
    Headers: Authorization: Bearer <token>, x-app-language: ru,
             x-app-type: fleet, x-app-version: 1.0.4

ВАЖНО: тело ответа пользователь не присылал, и неизвестно, является ли
"06FX40ZKENTAZ7VHKQS4916T3R" тестовым QR-кодом или кодом реального ТС из
боевого флита. Позитивные тесты, использующие этот код, ПОМЕЧЕНЫ как
требующие подтверждения — если это боевой код, лучше заменить на выделенный
QA-код (по аналогии с тестовыми номерами телефонов).
"""
import jsonschema
import pytest

from backend_tests.iquerix_b2b.schemas.auth_schemas import GENERIC_SUCCESS_SCHEMA

pytestmark = [pytest.mark.b2b, pytest.mark.regression]

# ДОПУЩЕНИЕ: взят из реального curl-примера пользователя — требует
# подтверждения, тестовый это код или боевой (см. докстринг файла).
REFERENCE_QR_CODE = "06FX40ZKENTAZ7VHKQS4916T3R"

# Заведомо несуществующий, но структурно похожий QR-код — безопасен для
# массовых негативных прогонов, не завязан на реальные данные.
NONEXISTENT_QR_CODE = "00000000000000000000000"


@pytest.mark.smoke
class TestQrPositive:

    def test_qr_returns_200_for_reference_code(self, b2b_authenticated_client, me_response):
        """
        ТРЕБУЕТ ПОДТВЕРЖДЕНИЯ: используется QR-код из реального curl-примера
        пользователя. Если это боевой код чужого ТС — заменить на QA-код.
        """
        response = b2b_authenticated_client.get_qr(code=REFERENCE_QR_CODE)
        assert response.status_code == 200, f"Получено {response.status_code}: {response.text}"
        assert response.json()["success"] is True

    def test_qr_response_matches_generic_schema(self, b2b_authenticated_client, me_response):
        """TODO: заменить на точную схему, когда будет реальный пример тела ответа."""
        response = b2b_authenticated_client.get_qr(code=REFERENCE_QR_CODE)
        jsonschema.validate(instance=response.json(), schema=GENERIC_SUCCESS_SCHEMA)

    def test_qr_response_time_within_sla(self, b2b_authenticated_client, me_response):
        response = b2b_authenticated_client.get_qr(code=REFERENCE_QR_CODE)
        assert response.elapsed.total_seconds() < 5


@pytest.mark.regression
class TestQrNegative:

    def test_qr_without_token(self, b2b_authenticated_client):
        response = b2b_authenticated_client.get_qr(code=NONEXISTENT_QR_CODE, token=False)
        assert response.status_code == 401

    def test_qr_with_invalid_token(self, b2b_authenticated_client):
        response = b2b_authenticated_client.get_qr(code=NONEXISTENT_QR_CODE, token="garbage.jwt.value")
        assert response.status_code == 401

    def test_qr_with_nonexistent_code(self, b2b_authenticated_client, me_response):
        """Синтаксически похожий, но не существующий QR-код — типичный сценарий повреждённой наклейки/опечатки."""
        response = b2b_authenticated_client.get_qr(code=NONEXISTENT_QR_CODE)
        assert response.status_code in (400, 404, 422), (
            f"Несуществующий QR-код должен давать 400/404/422, получено {response.status_code}: {response.text}"
        )
        assert response.status_code != 500

    @pytest.mark.parametrize("bad_code", [
        "",                     # пустой код (обрезанный путь)
        "a" * 500,              # огромная строка — потенциальный DoS
        "../../etc/passwd",     # попытка path traversal через path-параметр
        "<script>alert(1)</script>",
    ])
    def test_qr_with_malformed_code(self, b2b_authenticated_client, me_response, bad_code):
        response = b2b_authenticated_client.get_qr(code=bad_code)
        assert response.status_code != 500, (
            f"Код '{bad_code[:50]}...' не должен приводить к 500: {response.text[:200]}"
        )


@pytest.mark.regression
class TestQrTransportLevel:

    def test_qr_post_method_not_allowed(self, b2b_authenticated_client, auth_session):
        response = b2b_authenticated_client.post(
            f"/qr/{NONEXISTENT_QR_CODE}", headers={"Authorization": f"Bearer {auth_session['access_token']}"}
        )
        assert response.status_code in (401, 404, 405)
