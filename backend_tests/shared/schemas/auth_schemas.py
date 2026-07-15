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

# Ожидаемая форма для ответов с ошибкой (4xx) — уточнить у бэкенд-команды
# реальный формат error payload, пока держим гибкую схему.
LOGIN_ERROR_SCHEMA = {
    "type": "object",
    "properties": {
        "success": {"type": "boolean", "enum": [False]},
    },
    "required": ["success"],
}
