"""
Тестовый access/refresh токен iQuaRix OS.

ВАЖНО (временное решение):
  Токен взят из реального успешного /auth/verify лога и захардкожен здесь,
  чтобы можно было сразу писать и гонять тесты на защищённые эндпоинты
  (/auth/me, /s/statics/today, /s/operation/, /notification/), не дожидаясь
  полноценной auth-фикстуры "login -> verify -> token".

  У JWT есть `exp` — судя по payload, токен живёт ~1 час от `iat`. Это значит:
    - Этот конкретный токен, скорее всего, УЖЕ ПРОСРОЧЕН к моменту, когда вы
      будете гонять тесты (лог снят 2026-07-15/16).
    - Пока держим его как fallback-константу и переопределяем через переменную
      окружения IQUERIX_OS_ACCESS_TOKEN, чтобы можно было быстро подставить
      свежий токен вручную (скопировать из Charles/Proxyman/логов приложения),
      не трогая код тестов.

  TODO (правильное решение на следующем шаге):
    Добавить полноценный auth-flow фикстуру: login (/auth/login) -> verify
    (/auth/verify, код из SMS) -> access_token, и получать токен программно
    перед каждым прогоном регрессии, а не руками. До появления тестового
    SMS-стенда/моков — используем этот фиксированный токен.
"""
import os

# Токен из реального /auth/verify ответа (см. api_success_1784154641928.txt).
# Payload: user_id=019cb7c8-2ab4-72b9-a96c-5c39b4d49064, context_type=service,
# context_id (branch)=019d2f61-c74d-7564-bedb-07776cad69a3, iat=1784154678, exp=1784158278 (~1ч).
_FALLBACK_ACCESS_TOKEN = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJ1c2VyX2lkIjoiMDE5Y2I3YzgtMmFiNC03MmI5LWE5NmMtNWMzOWI0ZDQ5MDY0Iiwic2Vzc2lvbl9pZCI6"
    "IjAxOWY2N2U3LWU1ZmUtNzZiYi1iNGQ0LTgxNmU3Y2I3MGMzMCIsImlkIjoiMDE5ZjY3ZTctZTVmZS03NmJiLWI0ZDQtODVjNWM2NzA1ODcyIiwi"
    "Y29udGV4dF90eXBlIjoic2VydmljZSIsImNvbnRleHRfaWQiOiIwMTlkMmY2MS1jNzRkLTc1NjQtYmVkYi0wNzc3NmNhZDY5YTMiLCJjb250ZXh0"
    "X3VzZXJfaWQiOiIwMTljYjdjOC0yYWI0LTcyYjktYTk2Yy01YzM5YjRkNDkwNjQiLCJpYXQiOjE3ODQxNTQ2NzgsImV4cCI6MTc4NDE1ODI3OH0."
    "LFDAMprSfDDGc7yXY6orelwJvJUwYBRrAHozex3zFJ4"
)

_FALLBACK_REFRESH_TOKEN = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJ1c2VyX2lkIjoiMDE5Y2I3YzgtMmFiNC03MmI5LWE5NmMtNWMzOWI0ZDQ5MDY0Iiwic2Vzc2lvbl9pZCI6"
    "IjAxOWY2N2U3LWU1ZmUtNzZiYi1iNGQ0LTgxNmU3Y2I3MGMzMCIsImlkIjoiMDE5ZjY3ZTctZTVmZS03NmJiLWI0ZDQtODVjNWM2NzA1ODcyIiwi"
    "Y29udGV4dF90eXBlIjoic2VydmljZSIsImNvbnRleHRfaWQiOiIwMTlkMmY2MS1jNzRkLTc1NjQtYmVkYi0wNzc3NmNhZDY5YTMiLCJjb250ZXh0"
    "X3VzZXJfaWQiOiIwMTljYjdjOC0yYWI0LTcyYjktYTk2Yy01YzM5YjRkNDkwNjQiLCJpYXQiOjE3ODQxNTQ2NzgsImV4cCI6MTc4NDc1OTQ3OH0."
    "Q_v9aCIdonYJoYaGdWWyVlLK_zh7g6cxvQMXii3elmU"
)

ACCESS_TOKEN = os.getenv("IQUERIX_OS_ACCESS_TOKEN", _FALLBACK_ACCESS_TOKEN)
REFRESH_TOKEN = os.getenv("IQUERIX_OS_REFRESH_TOKEN", _FALLBACK_REFRESH_TOKEN)


def auth_header(token: str = ACCESS_TOKEN) -> dict:
    """Готовый заголовок Authorization для запросов к защищённым эндпоинтам."""
    return {"Authorization": f"Bearer {token}"}
