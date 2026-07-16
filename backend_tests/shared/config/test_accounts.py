"""
Пул тестовых номеров iQuaRix OS с ФИКСИРОВАННЫМ OTP-кодом.

Для этих номеров /auth/verify всегда принимает код 56563, независимо от
реального SMS. Это значит, что мы можем строить настоящий, живой, полностью
автоматический флоу авторизации на каждый прогон:

    /auth/login(phone)  -> signature
    /auth/verify(phone, code=56563, signature) -> access_token, refresh_token

...без ручного копирования токенов и без ожидания реального SMS.

ВАЖНО про rate-limit: /auth/login ограничивает повторный вход ПО НОМЕРУ
на ~10 минут (см. test_auth_login.py::TestLoginRateLimiting). Поэтому:
  - Под разные роли/сценарии тестов разведены РАЗНЫЕ номера из пула, чтобы
    они не конкурировали за один и тот же rate-limit.
  - Если нужно быстро перезапустить прогон несколько раз подряд (в течение
    10 минут) — сдвиньте индекс через переменные окружения ниже, чтобы
    взять "свежий" ещё не использованный номер из пула.
"""
import os

FIXED_OTP_CODE = "56563"

# Пул тестовых номеров с фиксированным OTP (заданы пользователем).
FIXED_OTP_TEST_PHONES = [
    "998990000000",
    "998980000000",
    "998970000000",
    "998960000000",
    "998950000000",
    "998940000000",
    "998930000000",
    "998920000000",
    "998910000000",
]


def _phone_by_index(env_var: str, default_index: int) -> str:
    """
    Достаёт номер из пула по индексу. Индекс можно переопределить через env,
    чтобы при повторных прогонах в течение 10 минут можно было взять
    следующий свободный (не под rate-limit'ом) номер, не трогая код.
    """
    index = int(os.getenv(env_var, str(default_index)))
    return FIXED_OTP_TEST_PHONES[index % len(FIXED_OTP_TEST_PHONES)]


# Номер, на котором строится "боевая" сессия (access_token) для тестов
# защищённых эндпоинтов: /auth/me, /s/statics/today, /s/operation/, /notification/.
AUTH_SESSION_PHONE = _phone_by_index("IQUERIX_OS_AUTH_SESSION_PHONE_INDEX", default_index=0)

# Номер для позитивных/rate-limit тестов самого /auth/login (test_auth_login.py).
# Отдельный от AUTH_SESSION_PHONE, чтобы не делить с ним квоту rate-limit'а.
LOGIN_TEST_PHONE = _phone_by_index("IQUERIX_OS_LOGIN_TEST_PHONE_INDEX", default_index=1)

# Номер для живого позитивного теста /auth/verify (test_auth_verify.py).
# Тоже отдельный — тест делает свой собственный login, чтобы получить
# свежий signature, и должен работать независимо от двух других.
VERIFY_TEST_PHONE = _phone_by_index("IQUERIX_OS_VERIFY_TEST_PHONE_INDEX", default_index=2)
