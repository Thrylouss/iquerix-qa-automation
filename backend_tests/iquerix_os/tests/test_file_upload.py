"""
Тесты POST /file/ — загрузка файла (multipart/form-data).

Референс успешного запроса (реальный лог):
    fields: {"purpose": "service_image"}, files: ["file"]
    -> 201 {"success": true, "data": {"id": "...", "key": "service_image/...",
            "accessibility_type": "public"}}
"""
import jsonschema
import pytest

from backend_tests.shared.schemas.os_branch_file_operation_schemas import FILE_UPLOAD_SUCCESS_SCHEMA

pytestmark = [pytest.mark.os, pytest.mark.regression]


@pytest.mark.smoke
class TestFileUploadPositive:

    def test_upload_returns_201(self, os_authenticated_client, auth_session):
        response = os_authenticated_client.upload_file(purpose="service_image")
        assert response.status_code == 201, f"Получено {response.status_code}: {response.text}"
        assert response.json()["success"] is True

    def test_upload_response_matches_schema(self, os_authenticated_client, auth_session):
        response = os_authenticated_client.upload_file(purpose="service_image")
        jsonschema.validate(instance=response.json(), schema=FILE_UPLOAD_SUCCESS_SCHEMA)

    def test_upload_key_contains_purpose_prefix(self, os_authenticated_client, auth_session):
        """Судя по логу, ключ файла в хранилище начинается с purpose (например 'service_image/...')."""
        data = os_authenticated_client.upload_file(purpose="service_image").json()["data"]
        assert data["key"].startswith("service_image/")

    def test_upload_accessibility_type_is_public(self, os_authenticated_client, auth_session):
        data = os_authenticated_client.upload_file(purpose="service_image").json()["data"]
        assert data["accessibility_type"] == "public"


class TestFileUploadNegative:

    def test_upload_without_file(self, os_authenticated_client, auth_session):
        response = os_authenticated_client.upload_file(omit_file=True)
        assert response.status_code in (400, 422), (
            f"Загрузка без файла должна отклоняться, получено {response.status_code}: {response.text}"
        )

    def test_upload_without_purpose(self, os_authenticated_client, auth_session):
        response = os_authenticated_client.upload_file(omit_purpose=True)
        assert response.status_code in (400, 422), (
            f"Загрузка без purpose должна отклоняться, получено {response.status_code}: {response.text}"
        )

    def test_upload_with_unknown_purpose_value(self, os_authenticated_client, auth_session):
        response = os_authenticated_client.upload_file(purpose="totally_made_up_purpose")
        assert response.status_code < 500, (
            f"Неизвестный purpose не должен ронять сервер, получено {response.status_code}: {response.text}"
        )

    def test_upload_without_token(self, os_authenticated_client):
        response = os_authenticated_client.upload_file(token=False)
        assert response.status_code == 401

    def test_upload_with_invalid_token(self, os_authenticated_client):
        response = os_authenticated_client.upload_file(token="garbage.jwt.value")
        assert response.status_code == 401

    def test_upload_with_non_image_file_for_image_purpose(self, os_authenticated_client, auth_session):
        """Текстовый файл вместо изображения для purpose='service_image' — не должен давать 500."""
        response = os_authenticated_client.upload_file(
            file_bytes=b"this is not an image, just plain text",
            filename="not_an_image.txt",
            mime_type="text/plain",
            purpose="service_image",
        )
        assert response.status_code < 500, f"Получено {response.status_code}: {response.text}"
