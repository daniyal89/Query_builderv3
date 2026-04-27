from fastapi.testclient import TestClient

from backend.app import app


def test_pick_save_path_post_returns_selected_path(monkeypatch):
    from backend.api.endpoints import system

    monkeypatch.setattr(system, "_pick_save_path_dialog", lambda suggested_name, default_extension: "C:/tmp/out.csv")

    client = TestClient(app)
    response = client.post(
        "/api/system/pick-save-path",
        json={"suggested_name": "out.csv", "default_extension": ".csv"},
    )

    assert response.status_code == 200
    assert response.json() == {"path": "C:/tmp/out.csv"}


def test_pick_save_path_post_handles_main_thread_runtime_error(monkeypatch):
    from backend.api.endpoints import system

    def _raise(*_args, **_kwargs):
        raise RuntimeError("main thread is not in main loop")

    monkeypatch.setattr(system, "_pick_save_path_dialog", _raise)

    client = TestClient(app)
    response = client.post(
        "/api/system/pick-save-path",
        json={"suggested_name": "out.csv", "default_extension": ".csv"},
    )

    assert response.status_code == 503
    assert "main thread" in response.json()["detail"].lower()
