from __future__ import annotations

import time

import httpx


class HttpClient:
    def __init__(self, timeout_seconds: float = 15.0, retries: int = 3, user_agent: str | None = None) -> None:
        self.timeout_seconds = timeout_seconds
        self.retries = retries
        self.user_agent = user_agent or "Mozilla/5.0 (compatible; DiscountParser/0.1)"

    def get_text(self, url: str) -> str:
        last_error: Exception | None = None
        headers = {
            "User-Agent": self.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ru,en;q=0.8",
        }
        for attempt in range(self.retries):
            try:
                with httpx.Client(timeout=self.timeout_seconds, follow_redirects=True, headers=headers) as client:
                    response = client.get(url)
                    response.raise_for_status()
                    return response.text
            except (httpx.HTTPError, httpx.TimeoutException) as exc:
                last_error = exc
                if attempt < self.retries - 1:
                    time.sleep(0.5 * (2**attempt))
        assert last_error is not None
        raise last_error
