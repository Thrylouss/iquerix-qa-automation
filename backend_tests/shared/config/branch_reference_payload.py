"""
Референсный ВАЛИДНЫЙ payload для POST /s/branch.

Основан на реальном успешном запросе из лога (api_success_1784160637228.txt),
но УКОРОЧЕН: в реальном логе service_catalog_items для service_type
'019d761a-4d09-7188-b64b-f2192e35bf42' содержал ~50+ элементов (видимо,
весь каталог услуг сервиса), здесь оставлены только первые 3 id.

ДОПУЩЕНИЕ (проверить на реальном окружении, если тест начнёт падать):
  Мы предполагаем, что service_catalog_items — это выбор ПОДМНОЖЕСТВА
  доступных id (а не обязательный полный список), поэтому укороченный
  список должен оставаться валидным. Если бэкенд на самом деле требует
  полный набор id — тест на создание филиала начнёт получать 400, и это
  будет сигналом поправить payload здесь.

Поле "images" в референсе пустое ([]) — тесты сами подставляют file_id,
полученный через реальный POST /file/ перед созданием филиала.
"""
import copy
import json
from pathlib import Path

_PAYLOAD_PATH = Path(__file__).parent / "branch_reference_payload.json"

with open(_PAYLOAD_PATH, "r", encoding="utf-8") as _f:
    _REFERENCE_PAYLOAD = json.load(_f)


def get_reference_branch_payload() -> dict:
    """Возвращает независимую копию референсного payload — безопасно мутировать в тестах."""
    return copy.deepcopy(_REFERENCE_PAYLOAD)
