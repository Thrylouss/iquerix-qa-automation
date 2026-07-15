"""
Базовый HTTP-клиент поверх requests.Session.
Используется всеми api_clients трёх проектов (OS / B2B / Admin).
"""
import logging
from typing import Any, Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger("qa.http")


class BaseApiClient:
    def __init__(self, base_url: str, default_headers: Optional[dict] = None, timeout: float = 15.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()

        retries = Retry(
            total=2,
            backoff_factor=0.5,
            status_forcelist=(502, 503, 504),
            allowed_methods=("GET",),  # POST не ретраим автоматически, чтобы не задвоить бизнес-эффекты
        )
        adapter = HTTPAdapter(max_retries=retries)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

        self.session.headers.update(default_headers or {})

    def request(self, method: str, path: str, **kwargs) -> requests.Response:
        url = f"{self.base_url}{path}"
        kwargs.setdefault("timeout", self.timeout)

        logger.info("--> %s %s | body=%s", method, url, kwargs.get("json"))
        response = self.session.request(method, url, **kwargs)
        logger.info("<-- %s %s | status=%s | body=%s", method, url, response.status_code, response.text[:1000])
        return response

    def post(self, path: str, **kwargs) -> requests.Response:
        return self.request("POST", path, **kwargs)

    def get(self, path: str, **kwargs) -> requests.Response:
        return self.request("GET", path, **kwargs)
