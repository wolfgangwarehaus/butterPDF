"""P1 — the curated public API, the AppBus factory seam, and run_app boot.

`import butterpdf` must stay light (only identity + version eager) so a fork's
configure() can run before the chrome's import-time font-scale read; the rest of
the public surface resolves lazily. The AppBus factory seam is the prerequisite
for inverting an app's richer bus (jellytoast's PlayerBus) onto butterpdf's base.
"""

from __future__ import annotations

import pytest


def test_public_api_resolves() -> None:
    import butterpdf

    assert callable(butterpdf.configure)  # eager
    assert callable(butterpdf.run_app)  # lazy
    assert butterpdf.AppWindow.__name__ == "AppWindow"
    assert callable(butterpdf.get_settings)

    from butterpdf.bus import AppBus

    assert butterpdf.AppBus is AppBus


def test_import_dough_stays_light() -> None:
    """`import butterpdf` must NOT pull the chrome (which reads QSettings at import
    time). design_tokens / window / app load only on first access."""
    import sys

    import butterpdf  # noqa: F401  (ensure imported)

    # configure must be eagerly available...
    assert "butterpdf.identity" in sys.modules
    # ...but accessing the lazy API is what imports the heavy modules. We can't
    # assert they're absent (other tests import them), so just prove the lazy
    # hook resolves a heavy module on demand.
    assert butterpdf.run_app.__module__ == "butterpdf.app"


def test_unknown_attr_raises() -> None:
    import butterpdf

    with pytest.raises(AttributeError):
        butterpdf.does_not_exist  # noqa: B018


@pytest.mark.usefixtures("qapp")
def test_appbus_factory_seam() -> None:
    """An app can register a bus subclass as the process-wide singleton, and the
    ordering guard rejects a late registration."""
    from butterpdf.bus import AppBus

    saved_inst, saved_factory = AppBus._instance, AppBus._factory
    try:
        AppBus._instance = None
        AppBus._factory = None

        class MyBus(AppBus):
            pass

        AppBus.set_factory(MyBus)
        bus = AppBus.get()
        assert isinstance(bus, MyBus)
        assert AppBus.get() is bus  # cached singleton

        # set_factory after the singleton exists is an ordering error.
        with pytest.raises(RuntimeError):
            AppBus.set_factory(MyBus)
    finally:
        AppBus._instance, AppBus._factory = saved_inst, saved_factory


@pytest.mark.usefixtures("qapp")
def test_run_app_boots(monkeypatch) -> None:
    """run_app builds + shows the app and runs the loop. Patch exec() so it
    doesn't block, and disable the single-instance lock so the test holds none."""
    from PySide6.QtWidgets import QApplication, QLabel

    import butterpdf

    monkeypatch.setattr(QApplication, "exec", lambda self: 0)
    code = butterpdf.run_app(lambda window: QLabel("hi"), single_instance=False)
    assert code == 0
