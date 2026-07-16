"""
JSON-схемы контрактов для /file/, /s/branch, /s/operation/draft.
Основаны на реальных успешных и ошибочных ответах из API-логов.
"""

FILE_UPLOAD_SUCCESS_SCHEMA = {
    "type": "object",
    "properties": {
        "success": {"type": "boolean", "enum": [True]},
        "data": {
            "type": "object",
            "properties": {
                "id": {"type": "string"},
                "key": {"type": "string"},
                "accessibility_type": {"type": "string"},
            },
            "required": ["id", "key", "accessibility_type"],
        },
    },
    "required": ["success", "data"],
}

BRANCH_CREATE_SUCCESS_SCHEMA = {
    "type": "object",
    "properties": {
        "success": {"type": "boolean", "enum": [True]},
        "data": {
            "type": "object",
            "properties": {"id": {"type": "string"}},
            "required": ["id"],
        },
    },
    "required": ["success", "data"],
}

BRANCH_LIST_SCHEMA = {
    "type": "object",
    "properties": {
        "success": {"type": "boolean", "enum": [True]},
        "data": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "name": {"type": "string"},
                    "lat": {"type": "number"},
                    "long": {"type": "number"},
                    "address": {"type": "string"},
                    "schedule": {"type": "object"},
                    "phone_number": {"type": "string"},
                    "user_count": {"type": "string"},
                    "primary_service_type": {"type": ["object", "null"]},
                    "images": {"type": "array"},
                },
                "required": ["id", "name", "lat", "long", "address", "phone_number"],
            },
        },
    },
    "required": ["success", "data"],
}

# Общий контракт ошибки (statusCode/error/message) — подтверждён на нескольких
# реальных эндпоинтах (/auth/login, /s/branch, /s/operation/draft).
GENERIC_API_ERROR_SCHEMA = {
    "type": "object",
    "properties": {
        "success": {"type": "boolean", "enum": [False]},
        "statusCode": {"type": "integer"},
        "error": {"type": "string"},
        "message": {"type": "string"},
    },
    "required": ["success", "statusCode", "error", "message"],
}
