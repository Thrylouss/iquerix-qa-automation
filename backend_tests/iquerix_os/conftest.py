import os

import pytest

from backend_tests.iquerix_os.api_clients.auth_client import OsAuthClient

# Согласно roadmap: URL окружений хранятся в .env / CI secrets
OS_BASE_URL = os.getenv("IQUERIX_OS_BASE_URL", "https://main.gandalf.iquarix.uz")

# Валидный тестовый номер — должен существовать в тестовом окружении (сидинг данных)
VALID_TEST_PHONE = os.getenv("IQUERIX_OS_TEST_PHONE", "998998987882")


@pytest.fixture(scope="session")
def os_auth_client() -> OsAuthClient:
    return OsAuthClient(base_url=OS_BASE_URL)


@pytest.fixture
def valid_phone_number() -> str:
    return VALID_TEST_PHONE
