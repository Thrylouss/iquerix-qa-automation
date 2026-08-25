"""
Трекер ограничения /auth/login — ПО КОНКРЕТНОМУ НОМЕРУ ТЕЛЕФОНА (не
глобально на весь бэкенд — такой лимит на все номера сразу для всех
клиентов был бы абсурдно агрессивным для реального продакшена; логически
и по смыслу антиспам-защита OTP всегда привязана к конкретному номеру,
для которого запрашивается код).

ПОДТВЕРЖДЕНО пользователем живым прогоном:
  1. Успешный /auth/login "занимает" ЭТОТ НОМЕР на 30 секунд — повторный
     /auth/login ЭТИМ ЖЕ номером в течение этого окна получает:
         403 {"error": "TOO_MANY_REQUESTS_WAIT_30_SECONDS", ...}
  2. Если вызвать /auth/login ЕЩЁ РАЗ этим же номером, пока это окно ещё
     не истекло, — ограничение эскалируется до 10 минут
     (TOO_MANY_REQUESTS_WAIT_10_MINUTES).
  3. Если пройти цикл ДО КОНЦА — то есть после успешного login сделать
     УСПЕШНЫЙ verify ЭТИМ ЖЕ номером, — ограничение для НЕГО снимается
     полностью немедленно.

Другие номера (структурно невалидные, мусорные, незарегистрированные)
лимит не расходуют вообще: сервер отклоняет их на 400/422/FORBIDDEN ДО
того, как добирается до анти-спам счётчика по номеру, поэтому клиент
помечает блокировку ТОЛЬКО когда видит успешный login (200) или явный
код ограничения (403 WAIT_...) — не для любого ответа подряд.

СТРАТЕГИЯ (вместо угадывания фиксированных пауз):
  - Каждый вызов login() ДЛЯ КОНКРЕТНОГО НОМЕРА сначала проверяет локально
    отслеженное время разблокировки ЭТОГО номера. Короткое ожидание —
    ждём. Длинное (похоже на эскалацию) — не ждём вслепую, кидаем
    понятную ошибку.
  - Успешный verify() СРАЗУ снимает блокировку ЭТОГО номера.
  - respect_lock=False форсирует немедленный реальный запрос в обход
    трекера — используется ТОЛЬКО в тесте, который намеренно проверяет
    сам факт срабатывания ограничения.

Все параметры — через env, без правки кода:
    IQUERIX_B2B_LOGIN_LOCK_SECONDS      (базовая длительность окна, 30 сек)
    IQUERIX_B2B_MAX_AUTO_WAIT_SECONDS   (потолок автоожидания, 35 сек)
"""
import os
import re
import threading
import time
from typing import Optional

LOGIN_LOCK_SECONDS = float(os.getenv("IQUERIX_B2B_LOGIN_LOCK_SECONDS", "30"))
MAX_AUTO_WAIT_SECONDS = float(os.getenv("IQUERIX_B2B_MAX_AUTO_WAIT_SECONDS", "35"))

# Небольшой запас поверх заявленной длительности — защита от гонки часов
# между клиентом и сервером.
_SAFETY_MARGIN_SECONDS = 1.0

_WAIT_CODE_PATTERN = re.compile(r"WAIT_(\d+)_(SECOND|MINUTE)S?", re.IGNORECASE)

_lock = threading.Lock()
# По-номерное состояние: phone_number -> time.monotonic() момент разблокировки.
_unlocked_at: dict = {}


class LoginStillLockedError(RuntimeError):
    """
    Клиент отказался делать реальный запрос для этого номера, т.к. по
    локальному трекеру ограничение ещё действует дольше
    MAX_AUTO_WAIT_SECONDS (похоже на эскалированные 10 минут) — чтобы не
    спровоцировать ещё одну эскалацию.
    """


def _parse_wait_seconds(error_code: Optional[str]) -> float:
    if not error_code:
        return LOGIN_LOCK_SECONDS
    match = _WAIT_CODE_PATTERN.search(error_code)
    if not match:
        return LOGIN_LOCK_SECONDS
    amount, unit = int(match.group(1)), match.group(2).upper()
    return float(amount * 60) if unit == "MINUTE" else float(amount)


def mark_login_success(phone_number: str) -> None:
    """Успешный login занимает ЭТОТ номер на LOGIN_LOCK_SECONDS, пока не закроется verify."""
    with _lock:
        _unlocked_at[phone_number] = time.monotonic() + LOGIN_LOCK_SECONDS + _SAFETY_MARGIN_SECONDS


def mark_rate_limited(phone_number: str, error_code: Optional[str]) -> None:
    """Сервер уже вернул 403 для ЭТОГО номера — фиксируем реальную длительность из ответа."""
    wait_seconds = _parse_wait_seconds(error_code)
    with _lock:
        _unlocked_at[phone_number] = time.monotonic() + wait_seconds + _SAFETY_MARGIN_SECONDS


def mark_verify_success(phone_number: str) -> None:
    """Успешный verify полностью снимает ограничение ДЛЯ ЭТОГО номера."""
    with _lock:
        _unlocked_at.pop(phone_number, None)


def seconds_until_unlocked(phone_number: str) -> float:
    with _lock:
        target = _unlocked_at.get(phone_number, 0.0)
    return max(0.0, target - time.monotonic())


def wait_or_raise_if_locked(phone_number: str) -> None:
    remaining = seconds_until_unlocked(phone_number)
    if remaining <= 0:
        return
    if remaining <= MAX_AUTO_WAIT_SECONDS:
        time.sleep(remaining)
        return
    raise LoginStillLockedError(
        f"/auth/login для номера {phone_number} заблокирован локальным трекером "
        f"ещё ~{remaining:.0f} сек — дольше порога автоожидания {MAX_AUTO_WAIT_SECONDS} сек. "
        f"Похоже, ограничение эскалировалось до длинного окна (10 минут). Реальный "
        f"запрос НЕ отправлен, чтобы не рисковать дальнейшей эскалацией."
    )
