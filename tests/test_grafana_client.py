import asyncio

import pytest

from src.utils.grafana import GrafanaClient


class FakeResponse:
    def __init__(self, status, payload=None):
        self.status = status
        self._payload = payload or []

    async def json(self):
        return self._payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class FakeSession:
    def __init__(self, response=None, raises=None):
        self._response = response
        self._raises = raises

    def get(self, *a, **kw):
        if self._raises:
            raise self._raises
        return self._response

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


def _run(client, monkeypatch, session):
    monkeypatch.setattr("src.utils.grafana.aiohttp.ClientSession", lambda **kw: session)
    return asyncio.run(client.get_active_alerts())


def test_returns_list_on_success(monkeypatch):
    client = GrafanaClient("http://grafana:3000", "token")
    payload = [{"labels": {"alertname": "HighCPU"}}]
    result = _run(client, monkeypatch, FakeSession(FakeResponse(200, payload)))
    assert result == payload


def test_empty_list_means_genuinely_no_alerts(monkeypatch):
    client = GrafanaClient("http://grafana:3000", "token")
    result = _run(client, monkeypatch, FakeSession(FakeResponse(200, [])))
    assert result == []


def test_returns_none_on_auth_failure(monkeypatch):
    client = GrafanaClient("http://grafana:3000", "bad-token")
    result = _run(client, monkeypatch, FakeSession(FakeResponse(401)))
    assert result is None, "401 must not look like 'no alerts'"


def test_returns_none_when_unreachable(monkeypatch):
    client = GrafanaClient("http://grafana:3000", "token")
    result = _run(client, monkeypatch, FakeSession(raises=OSError("connection refused")))
    assert result is None, "a dead API must not look like 'no alerts'"
