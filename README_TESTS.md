# Запуск тестов auth/login (iQuaRix OS)

```bash
pip install -r requirements.txt

# базовый запуск
pytest backend_tests/iquerix_os/tests/test_auth_login.py -v

# только smoke
pytest backend_tests/iquerix_os/tests -m smoke -v

# с Allure отчётом
pytest backend_tests/iquerix_os/tests --alluredir=allure-results
allure serve allure-results
```

Переменные окружения (см. conftest.py):
- IQUERIX_OS_BASE_URL (по умолчанию https://main.gandalf.iquarix.uz)
- IQUERIX_OS_TEST_PHONE (валидный тестовый номер для позитивных сценариев)

# Запуск тестов auth (iQuaRix B2B)

```bash
pip install -r requirements.txt

# все тесты B2B
pytest backend_tests/iquerix_b2b -v

# только smoke (быстрый набор для CI на каждый коммит)
pytest backend_tests/iquerix_b2b -m "b2b and smoke" -v

# только regression (полный набор, например ночной прогон)
pytest backend_tests/iquerix_b2b -m "b2b and regression" -v

# конкретный эндпоинт
pytest backend_tests/iquerix_b2b/tests/test_auth_login.py -v
pytest backend_tests/iquerix_b2b/tests/test_auth_verify.py -v
pytest backend_tests/iquerix_b2b/tests/test_auth_refresh.py -v

# с Allure отчётом
pytest backend_tests/iquerix_b2b --alluredir=allure-results
allure serve allure-results
```

Тестовые данные (пул номеров с фиксированным OTP, см. `iquerix_b2b/config/test_accounts.py`):
- `998017891234`, `998017892235`, `998017893235`
- фиксированный OTP-код: `43431`
- context: `fleet`

Переменные окружения (см. `iquerix_b2b/conftest.py`):
- `IQUERIX_B2B_BASE_URL` (по умолчанию `https://main.gandalf.iquarix.uz`)
- `IQUERIX_B2B_TEST_PHONE` — переопределить номер для позитивных тестов `/auth/login`
- `IQUERIX_B2B_AUTH_SESSION_PHONE_INDEX` / `IQUERIX_B2B_LOGIN_TEST_PHONE_INDEX` / `IQUERIX_B2B_VERIFY_TEST_PHONE_INDEX` —
  сдвинуть индекс номера в пуле, если текущий попал под rate-limit при повторном прогоне

**ВАЖНО:** часть тестов (rate-limit, коды ошибок структурной валидации) построена по
аналогии с уже подтверждённым поведением `iquerix_os` на том же бэкенде
(`main.gandalf.iquarix.uz`) — это ДОПУЩЕНИЯ, явно помеченные в докстрингах
`test_auth_login.py` / `test_auth_refresh.py`. При первом реальном прогоне
некоторые из них могут дать FAILED — это ожидаемо и является сигналом уточнить
контракт, а не багом самих тестов.
