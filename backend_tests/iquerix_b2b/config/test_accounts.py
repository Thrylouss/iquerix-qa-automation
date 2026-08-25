"""
Тестовые данные iQuaRix B2B.

Пул номеров с фиксированным OTP-кодом 43431 — ОФИЦИАЛЬНО зарегистрированные
QA-аккаунты (подтверждено пользователем), используются ТОЛЬКО для
позитивных сценариев (успешный login -> verify -> refresh и далее для
защищённых эндпоинтов), как и было явно указано.

ВАЖНО: номер 998017891234 БОЛЬШЕ НЕ ИСПОЛЬЗУЕТСЯ (по явному указанию
пользователя) — исключён из пула.

Контекст всех B2B auth-запросов — "fleet" (подтверждено логом).

Про ограничение /auth/login (30 сек / эскалация до 10 мин — см.
api_clients/login_lock_tracker.py): каждый login в этом наборе тестов
ВСЕГДА немедленно закрывается successful verify (включая позитивные тесты
самого login) — поэтому один и тот же номер безопасно переиспользуется в
разных ролях: к моменту следующего использования состояние уже "чистое".
"""
import os

FIXED_OTP_CODE = "43431"

FIXED_OTP_TEST_PHONES = [
    "998017892235",
    "998017893235",
]

B2B_CONTEXT = "fleet"


def _phone_by_index(env_var: str, default_index: int) -> str:
    """Достаёт номер из пула по индексу; можно сдвинуть через env без правки кода."""
    index = int(os.getenv(env_var, str(default_index)))
    return FIXED_OTP_TEST_PHONES[index % len(FIXED_OTP_TEST_PHONES)]


# Номер для "боевой" сессии (access_token для тестов защищённых эндпоинтов:
# /auth/refresh, /auth/me, /auth/me/session, /notification/, /service/filter,
# /qr, /f/shift/*, /f/vehicle/*).
AUTH_SESSION_PHONE = _phone_by_index("IQUERIX_B2B_AUTH_SESSION_PHONE_INDEX", default_index=0)

# Номер для позитивных тестов самого /auth/login (login немедленно
# закрывается verify — не оставляет "висящих" состояний).
LOGIN_TEST_PHONE = _phone_by_index("IQUERIX_B2B_LOGIN_TEST_PHONE_INDEX", default_index=1)

# Номер для живого позитивного флоу /auth/verify + его целевых негативных тестов.
VERIFY_TEST_PHONE = _phone_by_index("IQUERIX_B2B_VERIFY_TEST_PHONE_INDEX", default_index=0)
