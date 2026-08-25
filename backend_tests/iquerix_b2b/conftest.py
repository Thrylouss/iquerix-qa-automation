import os

import pytest

from backend_tests.iquerix_b2b.api_clients.auth_client import B2bAuthClient, RATE_LIMIT_ERROR_CODES
from backend_tests.iquerix_b2b.api_clients.authenticated_client import B2bAuthenticatedClient
from backend_tests.iquerix_b2b.api_clients.login_lock_tracker import LoginStillLockedError, wait_or_raise_if_locked
from backend_tests.iquerix_b2b.config.test_accounts import (
    AUTH_SESSION_PHONE,
    B2B_CONTEXT,
    FIXED_OTP_CODE,
    LOGIN_TEST_PHONE,
)

B2B_BASE_URL = os.getenv("IQUERIX_B2B_BASE_URL", "https://main.gandalf.iquarix.uz")
VALID_TEST_PHONE = os.getenv("IQUERIX_B2B_TEST_PHONE", LOGIN_TEST_PHONE)


@pytest.fixture(scope="session")
def b2b_auth_client() -> B2bAuthClient:
    return B2bAuthClient(base_url=B2B_BASE_URL)


@pytest.fixture(scope="session")
def b2b_authenticated_client() -> B2bAuthenticatedClient:
    return B2bAuthenticatedClient(base_url=B2B_BASE_URL)


def _extract_error_code(response) -> str:
    try:
        return response.json().get("error")
    except ValueError:
        return None


def _live_login(auth_client, phone_number: str, step_name: str):
    """
    Обёртка над auth_client.login() для "боевых" тестовых номеров.

    Наш локальный трекер (login_lock_tracker.py) стартует "чистым" при
    КАЖДОМ запуске pytest — но реальный лимит на СЕРВЕРЕ мог остаться
    активным с прошлого прогона (например, если предыдущий запуск был
    прерван до завершения verify). Поэтому: если первый живой вызов
    упирается в реальный 403 WAIT_..., клиент уже записал в трекер ТОЧНОЕ
    время снятия (распарсенное из ответа сервера) — используем это, чтобы
    один раз подождать ровно нужное время и повторить попытку, вместо
    того чтобы сразу валить тест.

    Если ожидание слишком долгое (LoginStillLockedError, похоже на
    эскалацию до 10 минут) — тест корректно скипается с понятной причиной.
    """
    try:
        response = auth_client.login(phone_number=phone_number, context=B2B_CONTEXT)
    except LoginStillLockedError as exc:
        pytest.skip(f"[{step_name}] {exc}")

    if response.status_code == 403 and _extract_error_code(response) in RATE_LIMIT_ERROR_CODES:
        try:
            wait_or_raise_if_locked(phone_number)
        except LoginStillLockedError as exc:
            pytest.skip(f"[{step_name}] {exc}")
        try:
            response = auth_client.login(phone_number=phone_number, context=B2B_CONTEXT)
        except LoginStillLockedError as exc:
            pytest.skip(f"[{step_name}] {exc}")

    return response


def _login_and_verify(auth_client, authenticated_client, phone_number: str, step_name: str) -> dict:
    """
    Общий живой флоу login -> verify. Всегда доводит цикл ДО КОНЦА
    (успешный verify) — это не только даёт токены, но и, согласно
    подтверждённой механике бэкенда, СРАЗУ снимает ограничение
    /auth/login ДЛЯ ЭТОГО НОМЕРА для следующих вызовов.
    """
    login_response = _live_login(auth_client, phone_number, step_name)
    if login_response.status_code != 200:
        pytest.fail(
            f"[{step_name}] Не удалось выполнить /auth/login для {phone_number}: "
            f"{login_response.status_code}: {login_response.text}."
        )
    signature = login_response.json()["signature"]

    verify_response = authenticated_client.verify(
        phone_number=phone_number, code=FIXED_OTP_CODE, signature=signature, context=B2B_CONTEXT
    )
    if verify_response.status_code != 200:
        pytest.fail(
            f"[{step_name}] Не удалось выполнить /auth/verify для {phone_number}: "
            f"{verify_response.status_code}: {verify_response.text}."
        )
    return verify_response.json()


@pytest.fixture(scope="session")
def auth_session(b2b_auth_client, b2b_authenticated_client):
    """
    Живая авторизация на весь прогон сессии для тестов защищённых
    эндпоинтов (/auth/refresh). Использует AUTH_SESSION_PHONE и всегда
    доводит login -> verify до конца.
    """
    tokens = _login_and_verify(b2b_auth_client, b2b_authenticated_client, AUTH_SESSION_PHONE, "auth_session")
    b2b_authenticated_client.set_default_token(tokens["access_token"])
    b2b_authenticated_client.set_default_refresh_token(tokens["refresh_token"])
    return {
        "phone_number": AUTH_SESSION_PHONE,
        "access_token": tokens["access_token"],
        "refresh_token": tokens["refresh_token"],
    }


@pytest.fixture(scope="session")
def me_response(b2b_authenticated_client, auth_session):
    """
    Единственный "живой" вызов /auth/me за сессию — переиспользуется всеми
    тестами защищённых эндпоинтов, которым просто нужен факт валидной
    авторизации (notification/service filter), чтобы не дублировать один
    и тот же вызов в каждом тесте.
    """
    response = b2b_authenticated_client.me()
    if response.status_code != 200:
        pytest.fail(
            f"/auth/me вернул {response.status_code} сразу после успешного /auth/verify — "
            f"неожиданно, токен должен быть валиден. Тело: {response.text}"
        )
    return response


@pytest.fixture(scope="session")
def valid_phone_number() -> str:
    """
    scope="session" намеренно: session-scope фикстура
    `successful_login_response` зависит от неё, а pytest не позволяет
    session-фикстуре зависеть от более узкой function-фикстуры.
    """
    return VALID_TEST_PHONE


@pytest.fixture(scope="session")
def successful_login_response(b2b_auth_client, b2b_authenticated_client, valid_phone_number):
    """
    Единственный "живой" успешный /auth/login за сессию для позитивных
    тестов самого login (схема/заголовки/тайминг). СРАЗУ закрывается через
    verify (без отдельного намеренного теста на rate-limit — он раньше
    нарочно оставлял login "висящим", что каскадно блокировало остальные
    тесты через TRY_AGAIN_LATER). Возвращает исходный ОТВЕТ LOGIN (не
    verify) — именно его проверяют тесты в TestLoginPositive.
    """
    response = _live_login(b2b_auth_client, valid_phone_number, "successful_login_response")
    if response.status_code != 200:
        pytest.fail(
            f"Не удалось получить базовый успешный логин для позитивных тестов "
            f"(номер {valid_phone_number}). Статус: {response.status_code}, тело: {response.text}"
        )
    signature = response.json()["signature"]
    cleanup_verify = b2b_authenticated_client.verify(
        phone_number=valid_phone_number, code=FIXED_OTP_CODE, signature=signature, context=B2B_CONTEXT
    )
    if cleanup_verify.status_code != 200:
        pytest.fail(
            f"Не удалось закрыть login для {valid_phone_number} через verify — "
            f"он останется 'висящим' и заблокирует остальные тесты (TRY_AGAIN_LATER): "
            f"{cleanup_verify.status_code}: {cleanup_verify.text}"
        )
    return response
