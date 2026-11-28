"""Headless render tests for the Streamlit app (streamlit.testing AppTest) on a temporary DB.

Covers: first-run seeding from an empty DB, every page renders without exception or error box, the sample upload path,
and the friendly missing-channel error.
"""
import os

import pytest
from streamlit.testing.v1 import AppTest

from src import config, db

TIMEOUT = 240


@pytest.fixture(scope="module", autouse=True)
def temp_db(tmp_path_factory):
    path = tmp_path_factory.mktemp("ui") / "ui.db"
    old = os.environ.get(config.DB_ENV_VAR)
    os.environ[config.DB_ENV_VAR] = str(path)
    yield path
    if old is None:
        os.environ.pop(config.DB_ENV_VAR, None)
    else:
        os.environ[config.DB_ENV_VAR] = old


def _run(page: str) -> AppTest:
    """Start from app.py (the real entrypoint, so page links resolve) and switch to `page`."""
    at = AppTest.from_file(str(config.ROOT / "app.py"), default_timeout=TIMEOUT)
    at.run()
    if page != "app.py":
        at.switch_page(page).run()
    assert not at.exception, [e.value for e in at.exception]
    return at


def _texts(at: AppTest) -> str:
    parts = [m.value for m in at.markdown] + [s.value for s in at.success] + [i.value for i in at.info]
    return "\n".join(str(p) for p in parts)


def test_home_seeds_demo_on_first_run(temp_db):
    at = _run("app.py")
    assert not at.error, [e.value for e in at.error]
    assert "Typicality, not health" in at.warning[0].value
    assert len(db.load_subject(config.DEMO_LONGITUDINAL_SUBJECT, db_path=temp_db)) == 13


def test_upload_sample(temp_db):
    at = _run("pages/1_Upload.py")
    at.button[1].click().run()                       # "Load sample (S060 eyes-open)"
    assert not at.exception and not at.error, [e.value for e in at.error]
    assert any("Composite" in s.value for s in at.success)
    assert len(db.load_subject("S060", db_path=temp_db)) == 1


def test_upload_sample_with_muse4_shows_missing_channels():
    at = _run("pages/1_Upload.py")
    at.selectbox[0].set_value("muse4").run()
    at.button[1].click().run()
    assert not at.exception
    assert any("AF7" in e.value and "missing" in e.value.lower() for e in at.error)


def test_session_page_renders():
    at = _run("pages/2_Session.py")
    assert not at.error, [e.value for e in at.error]
    labels = [m.label for m in at.metric]
    assert "Theta/beta ratio — rhythm" in labels and "Composite (typicality, 0–100)" in labels
    assert "reference, n = " in _texts(at)


def test_longitudinal_page_renders():
    at = _run("pages/3_Longitudinal.py")
    assert not at.error, [e.value for e in at.error]
    metrics = {m.label: m.value for m in at.metric}
    assert metrics["Sessions scored"] == "13"
    assert config.DEMO_LABEL in _texts(at)


def test_methodology_page_renders():
    at = _run("pages/4_Methodology.py")
    assert not at.error, [e.value for e in at.error]
    assert "FAIL" in at.warning[0].value and "ADR-013" in at.warning[0].value
