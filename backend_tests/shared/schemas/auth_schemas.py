"""
JSON-схемы контрактов ответов auth-эндпоинтов.
Валидация через jsonschema, как указано в roadmap (раздел "Схема/контракты API").
"""

LOGIN_SUCCESS_SCHEMA = {
    "type": "object",
    "properties": {
        "success": {"type": "boolean"},
        "signature": {
            "type": "string",
            # signature из реального успешного лога — hex-строка
            "pattern": "^[a-f0-9]+$",
            "minLength": 32,
        },
    },
    "required": ["success", "signature"],
    "additionalProperties": False,
}

# Реальный формат error payload подтверждён живым прогоном тестов:
# {"success": false, "statusCode": 403, "error": "USER_NOT_IN_SYSTEM", "message": "..."}
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

# Известные коды ошибок бэкенда (пополнять по мере обнаружения).
KNOWN_ERROR_CODES = {
    "USER_NOT_IN_SYSTEM": 403,
    "TOO_MANY_REQUESTS_WAIT_10_MINUTES": 403,
}
