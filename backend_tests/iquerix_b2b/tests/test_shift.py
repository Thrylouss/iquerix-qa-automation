"""
Тесты флоу смены (shift) водителя: /f/shift/draft -> /f/shift/{id}/read-mileage
-> /f/shift/{id}/start. iQuaRix B2B.

Референс запросов (curl, присланные пользователем):
    POST /f/shift/draft
        body: {"vehicle_qr_code": "06FX40ZKENTAZ7VHKQS4916T3R",
               "lat_draft_start": 41.32292210708471, "long_draft_start": 69.2780259756387}
    POST /f/shift/{shift_id}/read-mileage  (multipart/form-data)
        fields: lat, long, claimed_mileage, file=<фото одометра>
    POST /f/shift/{shift_id}/start
        body: {"started_at": "...", "lat_start": ..., "long_start": ...,
               "is_everything_all_right_start": true,
               "mileage_start_approved_by_driver": true, "comment_start": ""}

============================================================================
ВАЖНО — ЭТОТ ФЛОУ СТЕЙТФУЛ И ПОТЕНЦИАЛЬНО ЗАТРАГИВАЕТ РЕАЛЬНЫЕ ДАННЫЕ ФЛИТА
============================================================================
В отличие от auth-эндпоинтов (где easy откатить состояние через verify),
здесь КАЖДЫЙ успешный /f/shift/draft, вероятно, создаёт РЕАЛЬНУЮ запись
черновика смены для конкретного ТС и водителя. Пока НЕТ подтверждения:
  - является ли vehicle_qr_code/vehicle_id из curl-примеров пользователя
    выделенным QA-объектом (аналог тестовых номеров телефонов) или
    реальным ТС из боевого флита;
  - как ЗАВЕРШИТЬ/отменить черновик смены, если тест его создал (нужен ли
    отдельный DELETE/cancel эндпоинт, чтобы не блокировать ТС для реальных
    водителей и не копить мусорные черновики при каждом прогоне);
  - что произойдёт при повторном /f/shift/draft для уже имеющего активный
    черновик ТС (конфликт 409? тихая перезапись?).

ПОЭТОМУ: полный живой позитивный флоу (draft -> read-mileage -> start)
здесь НЕ реализован — только структурные/негативные/auth-тесty, которые
безопасны сами по себе (не создают реальных записей: используют
несуществующие/заведомо фейковые QR-коды, vehicle_id, shift_id).

Когда будут подтверждены тестовые vehicle_qr_code/vehicle_id (или создан
выделенный QA-автомобиль) и способ отката черновика — дописать:
  - живую позитивную цепочку с фикстурой session-scope, аналогичной
    auth_session, которая создаёт черновик, проходит read-mileage/start
    и ЛИБО отменяет его в teardown, ЛИБО использует специально выделенный,
    предназначенный только для тестов ТС.
"""
import pytest

pytestmark = [pytest.mark.b2b, pytest.mark.regression]

# Синтаксически валидные, но точно не существующие в системе значения —
# безопасны для массовых негативных прогонов, не создают реальных записей.
NONEXISTENT_QR_CODE = "00000000000000000000000"
NONEXISTENT_VEHICLE_ID = "00000000-0000-0000-0000-000000000000"
NONEXISTENT_SHIFT_ID = "00000000-0000-0000-0000-000000000000"


# ---------------------------------------------------------------------------
# POST /f/shift/draft
# ---------------------------------------------------------------------------

@pytest.mark.regression
class TestShiftDraftNegative:

    def test_shift_draft_without_token(self, b2b_authenticated_client):
        response = b2b_authenticated_client.create_shift_draft(vehicle_qr_code=NONEXISTENT_QR_CODE, token=False)
        assert response.status_code == 401

    def test_shift_draft_with_invalid_token(self, b2b_authenticated_client):
        response = b2b_authenticated_client.create_shift_draft(
            vehicle_qr_code=NONEXISTENT_QR_CODE, token="garbage.jwt.value"
        )
        assert response.status_code == 401

    def test_shift_draft_with_nonexistent_qr_code(self, b2b_authenticated_client, me_response):
        """Несуществующий/повреждённый QR-код — не должен создавать черновик и не должен давать 500."""
        response = b2b_authenticated_client.create_shift_draft(vehicle_qr_code=NONEXISTENT_QR_CODE)
        assert response.status_code in (400, 403, 404, 422), (
            f"Несуществующий QR должен давать 400/403/404/422, получено {response.status_code}: {response.text}"
        )
        assert response.status_code != 500

    @pytest.mark.parametrize("field_to_omit", ["vehicle_qr_code", "lat_draft_start", "long_draft_start"])
    def test_shift_draft_without_required_field(self, b2b_authenticated_client, me_response, field_to_omit):
        response = b2b_authenticated_client.create_shift_draft(
            vehicle_qr_code=NONEXISTENT_QR_CODE, omit_fields=[field_to_omit]
        )
        assert response.status_code in (400, 422), (
            f"Ожидалась ошибка валидации без '{field_to_omit}', "
            f"получено {response.status_code}: {response.text}"
        )

    def test_shift_draft_with_empty_body(self, b2b_authenticated_client, me_response):
        response = b2b_authenticated_client.create_shift_draft(raw_body={})
        assert response.status_code in (400, 422)

    @pytest.mark.parametrize("bad_lat", [999.0, -999.0, "not_a_number", None])
    def test_shift_draft_with_invalid_latitude(self, b2b_authenticated_client, me_response, bad_lat):
        """Широта вне диапазона [-90, 90] или неверного типа — типичная ошибка клиента при сбое GPS."""
        response = b2b_authenticated_client.create_shift_draft(
            vehicle_qr_code=NONEXISTENT_QR_CODE, lat_draft_start=bad_lat
        )
        assert response.status_code in (400, 422), (
            f"lat_draft_start='{bad_lat}' должен отклоняться, получено {response.status_code}: {response.text}"
        )

    def test_shift_draft_with_malformed_json_body(self, b2b_authenticated_client, me_response):
        broken_json = '{"vehicle_qr_code": "abc", "lat_draft_start": 1.0'
        response = b2b_authenticated_client.create_shift_draft(raw_body=broken_json)
        assert response.status_code in (400, 422, 500)


@pytest.mark.regression
class TestShiftDraftTransportLevel:

    def test_shift_draft_get_method_not_allowed(self, b2b_authenticated_client, auth_session):
        response = b2b_authenticated_client.get(
            "/f/shift/draft", headers={"Authorization": f"Bearer {auth_session['access_token']}"}
        )
        assert response.status_code in (401, 404, 405)


# ---------------------------------------------------------------------------
# POST /f/vehicle/{vehicle_id} -> уже покрыт test_vehicle.py; здесь только
# сам /f/shift/{shift_id}/read-mileage (multipart) и /f/shift/{shift_id}/start
# ---------------------------------------------------------------------------

@pytest.mark.regression
class TestShiftReadMileageNegative:

    def test_read_mileage_without_token(self, b2b_authenticated_client):
        response = b2b_authenticated_client.read_mileage(shift_id=NONEXISTENT_SHIFT_ID, token=False)
        assert response.status_code == 401

    def test_read_mileage_with_invalid_token(self, b2b_authenticated_client):
        response = b2b_authenticated_client.read_mileage(shift_id=NONEXISTENT_SHIFT_ID, token="garbage.jwt.value")
        assert response.status_code == 401

    def test_read_mileage_with_nonexistent_shift_id(self, b2b_authenticated_client, me_response):
        response = b2b_authenticated_client.read_mileage(shift_id=NONEXISTENT_SHIFT_ID)
        assert response.status_code in (400, 403, 404), (
            f"Несуществующий shift_id должен давать 400/403/404, получено {response.status_code}: {response.text}"
        )
        assert response.status_code != 500

    def test_read_mileage_without_file(self, b2b_authenticated_client, me_response):
        """Фото одометра — обязательная часть флоу, без файла должна быть ошибка валидации."""
        response = b2b_authenticated_client.read_mileage(shift_id=NONEXISTENT_SHIFT_ID, include_file=False)
        assert response.status_code in (400, 403, 404, 422), (
            f"Запрос без файла должен отклоняться, получено {response.status_code}: {response.text}"
        )

    @pytest.mark.parametrize("field_to_omit", ["lat", "long", "claimed_mileage"])
    def test_read_mileage_without_required_form_field(self, b2b_authenticated_client, me_response, field_to_omit):
        response = b2b_authenticated_client.read_mileage(shift_id=NONEXISTENT_SHIFT_ID, omit_fields=[field_to_omit])
        # Т.к. shift_id заведомо не существует, точный статус может быть
        # 400 (сначала валидация формы) или 403/404 (сначала проверка shift) —
        # главное, не 500 и не 200.
        assert response.status_code not in (200, 500), (
            f"Без '{field_to_omit}' не должно быть 200 или 500, получено {response.status_code}: {response.text}"
        )

    def test_read_mileage_with_negative_claimed_mileage(self, b2b_authenticated_client, me_response):
        """Отрицательный пробег — физически невозможное значение, типичная ошибка ручного ввода."""
        response = b2b_authenticated_client.read_mileage(shift_id=NONEXISTENT_SHIFT_ID, claimed_mileage=-100)
        assert response.status_code != 500

    def test_read_mileage_with_non_image_file(self, b2b_authenticated_client, me_response):
        """Загрузка не-изображения (например, текстового файла) под видом фото одометра."""
        response = b2b_authenticated_client.read_mileage(
            shift_id=NONEXISTENT_SHIFT_ID,
            file_content=b"this is not an image, just plain text",
            file_name="not_a_photo.txt",
            file_content_type="text/plain",
        )
        assert response.status_code != 500, f"Не-изображение не должно приводить к 500: {response.text[:200]}"

    def test_read_mileage_with_oversized_file(self, b2b_authenticated_client, me_response):
        """Очень большой файл (потенциальный DoS через загрузку) должен либо отклоняться, либо ограничиваться."""
        large_content = b"0" * (10 * 1024 * 1024)  # 10 MB
        response = b2b_authenticated_client.read_mileage(
            shift_id=NONEXISTENT_SHIFT_ID, file_content=large_content, file_name="huge.jpg"
        )
        assert response.status_code != 500, f"Огромный файл не должен приводить к 500: {response.status_code}"


@pytest.mark.regression
class TestShiftReadMileageTransportLevel:

    def test_read_mileage_get_method_not_allowed(self, b2b_authenticated_client, auth_session):
        response = b2b_authenticated_client.get(
            f"/f/shift/{NONEXISTENT_SHIFT_ID}/read-mileage",
            headers={"Authorization": f"Bearer {auth_session['access_token']}"},
        )
        assert response.status_code in (401, 404, 405)


# ---------------------------------------------------------------------------
# POST /f/shift/{shift_id}/start
# ---------------------------------------------------------------------------

@pytest.mark.regression
class TestShiftStartNegative:

    def test_start_shift_without_token(self, b2b_authenticated_client):
        response = b2b_authenticated_client.start_shift(shift_id=NONEXISTENT_SHIFT_ID, token=False)
        assert response.status_code == 401

    def test_start_shift_with_invalid_token(self, b2b_authenticated_client):
        response = b2b_authenticated_client.start_shift(shift_id=NONEXISTENT_SHIFT_ID, token="garbage.jwt.value")
        assert response.status_code == 401

    def test_start_shift_with_nonexistent_shift_id(self, b2b_authenticated_client, me_response):
        response = b2b_authenticated_client.start_shift(shift_id=NONEXISTENT_SHIFT_ID)
        assert response.status_code in (400, 403, 404), (
            f"Несуществующий shift_id должен давать 400/403/404, получено {response.status_code}: {response.text}"
        )
        assert response.status_code != 500

    @pytest.mark.parametrize("field_to_omit", [
        "started_at", "lat_start", "long_start",
        "is_everything_all_right_start", "mileage_start_approved_by_driver",
    ])
    def test_start_shift_without_required_field(self, b2b_authenticated_client, me_response, field_to_omit):
        """comment_start НЕ включён в параметризацию — судя по реальному примеру, может быть пустой строкой,
        вероятно опционален."""
        response = b2b_authenticated_client.start_shift(shift_id=NONEXISTENT_SHIFT_ID, omit_fields=[field_to_omit])
        assert response.status_code not in (200, 500), (
            f"Без '{field_to_omit}' не должно быть 200 или 500, получено {response.status_code}: {response.text}"
        )

    def test_start_shift_with_is_everything_all_right_false(self, b2b_authenticated_client, me_response):
        """
        is_everything_all_right_start=false — легитимный сценарий (водитель
        сообщает о проблеме с ТС при приёмке). Не должен ломать эндпоинт
        структурно, даже если сам shift_id не существует.
        """
        response = b2b_authenticated_client.start_shift(
            shift_id=NONEXISTENT_SHIFT_ID, is_everything_all_right_start=False, comment_start="Есть царапина"
        )
        assert response.status_code != 500

    def test_start_shift_with_wrong_type_for_boolean_field(self, b2b_authenticated_client, me_response):
        response = b2b_authenticated_client.start_shift(
            shift_id=NONEXISTENT_SHIFT_ID, raw_body={
                "started_at": "2026-08-25T00:17:49Z",
                "lat_start": 41.0, "long_start": 69.0,
                "is_everything_all_right_start": "yes",  # должен быть bool
                "mileage_start_approved_by_driver": True,
                "comment_start": "",
            }
        )
        assert response.status_code in (400, 403, 404, 422), (
            f"Строковый is_everything_all_right_start должен отклоняться или не найти shift, "
            f"получено {response.status_code}: {response.text}"
        )

    def test_start_shift_with_malformed_started_at(self, b2b_authenticated_client, me_response):
        """started_at не в формате ISO8601 — типичная ошибка при неправильной локальной сериализации даты на клиенте."""
        response = b2b_authenticated_client.start_shift(shift_id=NONEXISTENT_SHIFT_ID, started_at="not-a-date")
        assert response.status_code != 500

    def test_start_shift_with_malformed_json_body(self, b2b_authenticated_client, me_response):
        broken_json = '{"started_at": "2026-08-25T00:17:49Z", "lat_start": 41.0'
        response = b2b_authenticated_client.start_shift(shift_id=NONEXISTENT_SHIFT_ID, raw_body=broken_json)
        assert response.status_code in (400, 422, 500)


@pytest.mark.regression
class TestShiftStartTransportLevel:

    def test_start_shift_get_method_not_allowed(self, b2b_authenticated_client, auth_session):
        response = b2b_authenticated_client.get(
            f"/f/shift/{NONEXISTENT_SHIFT_ID}/start",
            headers={"Authorization": f"Bearer {auth_session['access_token']}"},
        )
        assert response.status_code in (401, 404, 405)
