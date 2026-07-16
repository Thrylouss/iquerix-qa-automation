import os

import pytest

from backend_tests.iquerix_os.api_clients.auth_client import OsAuthClient
from backend_tests.iquerix_os.api_clients.authenticated_client import OsAuthenticatedClient
from backend_tests.shared.config.test_accounts import (
    AUTH_SESSION_PHONE,
    FIXED_OTP_CODE,
    LOGIN_TEST_PHONE,
)

# Согласно roadmap: URL окружений хранятся в .env / CI secrets
OS_BASE_URL = os.getenv("IQUERIX_OS_BASE_URL", "https://main.gandalf.iquarix.uz")

# Номер для тестов самого /auth/login (test_auth_login.py) — теперь берётся
# из пула с фиксированным OTP (shared/config/test_accounts.py), а не абстрактный
# "любой валидный номер". Можно переопределить через env для разовой отладки.
VALID_TEST_PHONE = os.getenv("IQUERIX_OS_TEST_PHONE", LOGIN_TEST_PHONE)

# Бэкенд ограничивает /auth/login по номеру телефона: после успешного логина
# повторные попытки этим же номером получают 403 TOO_MANY_REQUESTS_WAIT_10_MINUTES.
RATE_LIMIT_ERROR_CODE = "TOO_MANY_REQUESTS_WAIT_10_MINUTES"


@pytest.fixture(scope="session")
def os_auth_client() -> OsAuthClient:
    return OsAuthClient(base_url=OS_BASE_URL)


@pytest.fixture(scope="session")
def os_authenticated_client() -> OsAuthenticatedClient:
    """
    Клиент для /auth/verify, /auth/me, /s/statics/today, /s/operation/, /notification/.
    Токен НЕ хардкодится — выставляется фикстурой `auth_session` ниже через
    настоящий /auth/login -> /auth/verify флоу на номере с фиксированным OTP.
    """
    return OsAuthenticatedClient(base_url=OS_BASE_URL)


@pytest.fixture(scope="session")
def auth_session(os_auth_client, os_authenticated_client):
    """
    Настоящая, живая авторизация на весь прогон сессии — без ручного
    копирования токенов и без ожидания реального SMS:

        /auth/login(AUTH_SESSION_PHONE)   -> signature
        /auth/verify(..., code=FIXED_OTP_CODE, signature) -> access_token

    Номер AUTH_SESSION_PHONE входит в пул с фиксированным OTP-кодом 56563
    (shared/config/test_accounts.py) — verify всегда его принимает, поэтому
    флоу воспроизводим на 100% при каждом прогоне.

    Полученный access_token выставляется как default_token в os_authenticated_client,
    так что все тесты /auth/me, /s/statics/today, /s/operation/, /notification/
    получают его автоматически, не передавая token= вручную.
    """
    login_response = os_auth_client.login(phone_number=AUTH_SESSION_PHONE, context="service")
    if login_response.status_code != 200:
        pytest.fail(
            f"Не удалось выполнить /auth/login для AUTH_SESSION_PHONE={AUTH_SESSION_PHONE}: "
            f"{login_response.status_code}: {login_response.text}. "
            f"Возможно, номер под rate-limit'ом с прошлого прогона (10 минут) — "
            f"сдвиньте IQUERIX_OS_AUTH_SESSION_PHONE_INDEX на другой номер из пула."
        )
    signature = login_response.json()["signature"]

    verify_response = os_authenticated_client.verify(
        phone_number=AUTH_SESSION_PHONE, code=FIXED_OTP_CODE, signature=signature, context="service"
    )
    if verify_response.status_code != 200:
        pytest.fail(
            f"Не удалось выполнить /auth/verify для AUTH_SESSION_PHONE={AUTH_SESSION_PHONE}: "
            f"{verify_response.status_code}: {verify_response.text}"
        )
    tokens = verify_response.json()
    os_authenticated_client.set_default_token(tokens["access_token"])

    return {
        "phone_number": AUTH_SESSION_PHONE,
        "access_token": tokens["access_token"],
        "refresh_token": tokens["refresh_token"],
    }


@pytest.fixture(scope="session")
def me_response(os_authenticated_client, auth_session):
    """
    Единственный "живой" вызов /auth/me за сессию — переиспользуется всеми
    тестами защищённых эндпоинтов, которым просто нужен факт валидной
    авторизации (statics/operations/notifications), чтобы не дублировать
    один и тот же вызов в каждом тесте.
    """
    response = os_authenticated_client.me()
    if response.status_code != 200:
        pytest.fail(
            f"/auth/me вернул {response.status_code} сразу после успешного /auth/verify — "
            f"неожиданно, токен должен быть валиден. Тело: {response.text}"
        )
    return response


@pytest.fixture(scope="session")
def uploaded_service_image(os_authenticated_client, auth_session):
    """
    Единственный "живой" POST /file/ за сессию — переиспользуется тестами
    /s/branch (которым нужен реальный file_id для поля images), чтобы не
    плодить лишние загруженные файлы на каждый тест.
    """
    response = os_authenticated_client.upload_file(purpose="service_image")
    if response.status_code != 201:
        pytest.fail(f"Не удалось загрузить тестовое изображение: {response.status_code}: {response.text}")
    return response.json()["data"]


@pytest.fixture(scope="session")
def created_branch(os_authenticated_client, uploaded_service_image):
    """
    Единственный "живой" POST /s/branch за сессию — создаёт тестовый филиал
    с реальным file_id из uploaded_service_image, переиспользуется тестами
    /s/operation/draft, которым нужен существующий service_branch_id.

    ВНИМАНИЕ: это реальная запись в тестовом окружении (не откатывается
    автоматически) — так же, как и оригинальный ручной прогон в приложении.
    """
    from backend_tests.shared.config.branch_reference_payload import get_reference_branch_payload

    payload = get_reference_branch_payload()
    payload["images"] = [{"file_id": uploaded_service_image["id"], "sort_order": 0}]

    response = os_authenticated_client.create_branch(payload=payload)
    if response.status_code != 200:
        pytest.fail(f"Не удалось создать тестовый филиал: {response.status_code}: {response.text}")
    return response.json()["data"]


@pytest.fixture
def valid_phone_number() -> str:
    return VALID_TEST_PHONE


@pytest.fixture(scope="session")
def successful_login_response(os_auth_client, valid_phone_number):
    """
    Единственный "живой" успешный вызов /auth/login за весь прогон сессии
    (для test_auth_login.py — независимый номер из пула, отдельный от
    AUTH_SESSION_PHONE, чтобы не делить с ним rate-limit).
    """
    response = os_auth_client.login(phone_number=valid_phone_number, context="service")
    if response.status_code != 200:
        pytest.fail(
            "Не удалось получить базовый успешный логин для позитивных тестов "
            f"(возможно, номер {valid_phone_number} уже под rate-limit'ом с прошлого "
            f"прогона — подождите 10 минут или сдвиньте IQUERIX_OS_LOGIN_TEST_PHONE_INDEX). "
            f"Статус: {response.status_code}, тело: {response.text}"
        )
    return response


@pytest.fixture(autouse=True)
def skip_if_rate_limited(request, os_auth_client):
    """
    Guard от каскадных падений: если valid_phone_number уже словил
    TOO_MANY_REQUESTS_WAIT_10_MINUTES в текущем прогоне (флаг детектится
    самим клиентом в OsAuthClient.login), все последующие тесты, которым
    нужен именно этот номер, скипаем с понятной причиной — вместо того
    чтобы получать десяток непонятных FAILED подряд.
    """
    if os_auth_client.rate_limited and "valid_phone_number" in request.fixturenames:
        pytest.skip(
            f"Пропущено: valid_phone_number уже под rate-limit'ом "
            f"({RATE_LIMIT_ERROR_CODE}) в текущем прогоне сессии. "
            f"Подождите 10 минут или сдвиньте IQUERIX_OS_LOGIN_TEST_PHONE_INDEX."
        )
    yield
