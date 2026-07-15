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
