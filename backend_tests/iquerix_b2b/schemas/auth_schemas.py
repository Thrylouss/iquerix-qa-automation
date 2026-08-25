"""
JSON-схемы контрактов ответов auth-эндпоинтов iQuaRix B2B.
Построены на реальных живых логах, присланных пользователем.
"""

LOGIN_SUCCESS_SCHEMA = {
    "type": "object",
    "properties": {
        "success": {"type": "boolean", "enum": [True]},
        "signature": {"type": "string", "pattern": "^[a-f0-9]+$", "minLength": 32},
    },
    "required": ["success", "signature"],
    "additionalProperties": False,
}

LOGIN_ERROR_SCHEMA = {
    "type": "object",
    "properties": {
        "success": {"type": "boolean", "enum": [False]},
        "statusCode": {"type": "integer"},
        "error": {"type": "string"},
        "message": {"type": "string"},
    },
    "required": ["success", "statusCode", "error", "message"],
}

VERIFY_SUCCESS_SCHEMA = {
    "type": "object",
    "properties": {
        "success": {"type": "boolean", "enum": [True]},
        "access_token": {"type": "string", "minLength": 10},
        "refresh_token": {"type": "string", "minLength": 10},
    },
    "required": ["success", "access_token", "refresh_token"],
}

# /auth/refresh возвращает ту же форму, что и /auth/verify (подтверждено логом).
REFRESH_SUCCESS_SCHEMA = VERIFY_SUCCESS_SCHEMA

# Минимальная, консервативная схема для /auth/me, /auth/me/session,
# /notification/, /service/filter — ТОЛЬКО success:true подтверждён формой
# curl-запросов пользователя (тела ОТВЕТОВ присланы не были, поэтому
# конкретные поля данных здесь намеренно НЕ фиксируются — уточнить, когда
# будут реальные тела ответов, и заменить на точную схему по образцу
# VERIFY_SUCCESS_SCHEMA/LOGIN_SUCCESS_SCHEMA).
GENERIC_SUCCESS_SCHEMA = {
    "type": "object",
    "properties": {
        "success": {"type": "boolean", "enum": [True]},
    },
    "required": ["success"],
}

# Известные коды ошибок бэкенда B2B (пополнять по мере обнаружения живыми прогонами).
KNOWN_ERROR_CODES = {
    "FORBIDDEN": 403,                              # незарегистрированный номер
    "TOO_MANY_REQUESTS_WAIT_30_SECONDS": 403,       # 1-й уровень лимита /auth/login
    "TOO_MANY_REQUESTS_WAIT_10_MINUTES": 403,       # эскалированный уровень
    "UPDATE_REQUIRED": 426,                         # устаревший x-app-version
}
