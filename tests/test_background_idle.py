import asyncio
import time

from fastapi.testclient import TestClient

from app.services import activity, background


def _make_idle(monkeypatch) -> None:
    monkeypatch.setattr(activity, "_last_activity", time.monotonic() - 3600)


def test_is_idle_disabled_when_threshold_zero(monkeypatch) -> None:
    _make_idle(monkeypatch)
    assert activity.is_idle(0) is False
    assert activity.is_idle(600) is True


def test_healthz_does_not_count_as_activity(monkeypatch) -> None:
    from app.main import app

    _make_idle(monkeypatch)
    client = TestClient(app)

    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert activity.is_idle(600) is True

    client.get("/", follow_redirects=False)
    assert activity.is_idle(600) is False


def _run_one_iteration() -> None:
    async def scenario() -> None:
        stop_event = asyncio.Event()
        task = asyncio.create_task(background.background_maintenance(stop_event))
        await asyncio.sleep(0.05)
        stop_event.set()
        await task

    asyncio.run(scenario())


def test_background_skips_db_ticks_when_idle(monkeypatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(background, "_link_lost_tick", lambda: calls.append("link_lost"))
    monkeypatch.setattr(background.settings, "background_idle_after_seconds", 600)

    _make_idle(monkeypatch)
    _run_one_iteration()
    assert calls == []

    activity.mark_activity()
    _run_one_iteration()
    assert calls == ["link_lost"]


def test_background_never_idles_with_default_threshold(monkeypatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(background, "_link_lost_tick", lambda: calls.append("link_lost"))
    monkeypatch.setattr(background.settings, "background_idle_after_seconds", 0)

    _make_idle(monkeypatch)
    _run_one_iteration()
    assert calls == ["link_lost"]
