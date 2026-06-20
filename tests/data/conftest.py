"""Shared test doubles for the data-layer tests.

`FakeResponse` mimics the slice of `requests.Response` the adapters use
(`.text`, `.json()`, `.raise_for_status()`), so tests never touch the network.
"""

from __future__ import annotations

import requests


class FakeResponse:
    def __init__(self, *, text: str = "", json_data=None, status_code: int = 200):
        self._text = text
        self._json = json_data
        self.status_code = status_code

    @property
    def text(self) -> str:
        return self._text

    def json(self):
        return self._json

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")
