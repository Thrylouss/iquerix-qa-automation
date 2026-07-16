"""
JSON-схемы контрактов ответов авторизованных эндпоинтов iQuaRix OS.
Основаны на реальных успешных ответах из API-логов.
"""

VERIFY_SUCCESS_SCHEMA = {
    "type": "object",
    "properties": {
        "success": {"type": "boolean", "enum": [True]},
        "access_token": {"type": "string", "minLength": 10},
        "refresh_token": {"type": "string", "minLength": 10},
    },
    "required": ["success", "access_token", "refresh_token"],
}

ME_SUCCESS_SCHEMA = {
    "type": "object",
    "properties": {
        "success": {"type": "boolean", "enum": [True]},
        "data": {
            "type": "object",
            "properties": {
                "id": {"type": "string"},
                "phone_number": {"type": "string"},
                "first_name": {"type": ["string", "null"]},
                "last_name": {"type": ["string", "null"]},
                "status": {"type": "string"},
                "branch_id": {"type": ["string", "null"]},
                "role": {"type": "object"},
                "service": {"type": "object"},
            },
            "required": ["id", "phone_number", "status", "role"],
        },
    },
    "required": ["success", "data"],
}

STATICS_TODAY_SCHEMA = {
    "type": "object",
    "properties": {
        "success": {"type": "boolean", "enum": [True]},
        "data": {
            "type": "object",
            "properties": {
                "revenue": {
                    "type": "object",
                    "properties": {
                        "today": {"type": "number"},
                        "percent_change": {"type": "number"},
                    },
                    "required": ["today", "percent_change"],
                },
                "service_count": {
                    "type": "object",
                    "properties": {
                        "today": {"type": "number"},
                        "percent_change": {"type": "number"},
                    },
                    "required": ["today", "percent_change"],
                },
                "last_operation": {"type": ["object", "null"]},
            },
            "required": ["revenue", "service_count"],
        },
    },
    "required": ["success", "data"],
}

OPERATIONS_LIST_SCHEMA = {
    "type": "object",
    "properties": {
        "success": {"type": "boolean", "enum": [True]},
        "data": {
            "type": "object",
            "properties": {
                "service_operations": {"type": "array"},
                "in_progress_count": {"type": "integer"},
                "cancelled_count": {"type": "integer"},
                "completed_count": {"type": "integer"},
                "page": {"type": "integer"},
                "total_pages": {"type": "integer"},
            },
            "required": [
                "service_operations", "in_progress_count", "cancelled_count",
                "completed_count", "page", "total_pages",
            ],
        },
    },
    "required": ["success", "data"],
}

NOTIFICATIONS_LIST_SCHEMA = {
    "type": "object",
    "properties": {
        "success": {"type": "boolean", "enum": [True]},
        "data": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "title": {"type": "string"},
                    "body": {"type": "string"},
                    "sender_type": {"type": "string"},
                    "created_at": {"type": "string"},
                    "context_type": {"type": "string"},
                    "read": {"type": "boolean"},
                },
                "required": ["id", "title", "body", "sender_type", "created_at", "read"],
            },
        },
    },
    "required": ["success", "data"],
}

# Общая форма для ответов об ошибке авторизации (401/403) — по аналогии с auth/login,
# уточнить при первом реальном негативном ответе бэкенда.
UNAUTHORIZED_ERROR_SCHEMA = {
    "type": "object",
    "properties": {
        "success": {"type": "boolean", "enum": [False]},
    },
    "required": ["success"],
}
