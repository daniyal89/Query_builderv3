from __future__ import annotations

import os
import re
import shutil
import time
from pathlib import Path

import pytest
from backend.services.job_runtime import job_runtime
from backend.utils.rate_limits import DEFAULT_RATE_LIMIT_POLICIES, rate_limiter


REPO_ROOT = Path(__file__).resolve().parents[1]
WINDOWS_TMP_ROOT = Path("C:/tmp/query_builderv3_pytest")
WORKSPACE_TMP_ROOT = REPO_ROOT / "test-tmp"


def _candidate_test_tmp_roots() -> list[Path]:
    override = os.environ.get("QUERY_BUILDER_TEST_TMPDIR", "").strip()
    if override:
        return [Path(override).expanduser()]
    if os.name == "nt":
        return [WINDOWS_TMP_ROOT, WORKSPACE_TMP_ROOT]
    return [WORKSPACE_TMP_ROOT]


def _safe_node_name(nodeid: str) -> str:
    collapsed = re.sub(r"[^A-Za-z0-9._-]+", "-", nodeid).strip("-")
    return collapsed[:80] or "test"


def _remove_tree_with_retries(path: Path) -> None:
    if not path.exists():
        return

    for _ in range(4):
        shutil.rmtree(path, ignore_errors=True)
        if not path.exists():
            return
        time.sleep(0.15)


def _reset_rate_limit_policies() -> None:
    rate_limiter.reset()
    for name, policy in DEFAULT_RATE_LIMIT_POLICIES.items():
        rate_limiter.set_policy(name, policy)


@pytest.fixture(scope="session")
def _test_tmp_root() -> Path:
    last_error: Exception | None = None

    for root in _candidate_test_tmp_roots():
        try:
            root.mkdir(parents=True, exist_ok=True)
            yield root
            _remove_tree_with_retries(root)
            return
        except Exception as exc:  # pragma: no cover - exercised only in restricted environments
            last_error = exc

    if last_error is not None:
        raise RuntimeError(f"Could not create a writable pytest temp root: {last_error}") from last_error
    raise RuntimeError("Could not create a writable pytest temp root.")


@pytest.fixture
def tmp_path(request: pytest.FixtureRequest, _test_tmp_root: Path) -> Path:
    base_name = _safe_node_name(request.node.nodeid)
    candidate = _test_tmp_root / base_name

    suffix = 0
    while candidate.exists():
        suffix += 1
        candidate = _test_tmp_root / f"{base_name}-{suffix}"

    candidate.mkdir(parents=True, exist_ok=False)
    yield candidate
    _remove_tree_with_retries(candidate)


@pytest.fixture(autouse=True)
def reset_rate_limits() -> None:
    _reset_rate_limit_policies()
    yield
    _reset_rate_limit_policies()


@pytest.fixture(autouse=True)
def reset_job_runtime(tmp_path: Path) -> None:
    job_runtime.reset_for_tests(tmp_path / "job_store.sqlite3")
    yield
    job_runtime.reset_for_tests(tmp_path / "job_store.sqlite3")
