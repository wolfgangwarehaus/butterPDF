"""butterpdf — the wolfgang warehaus app base. See docs/PHILOSOPHY.md."""

from butterpdf.identity import configure


def _resolve_version() -> str:
    """The single version source (docs/BAKING.md §2 principle 4). In a built
    install, setuptools-scm has written ``butterpdf/_version.py`` from the git tag.
    In a raw source checkout it hasn't, so fall back to the installed-package
    metadata, then to a sentinel — never hardcode a number that could drift."""
    try:
        from butterpdf._version import version  # generated at build by setuptools-scm

        return version
    except ImportError:
        pass
    try:
        from importlib.metadata import PackageNotFoundError, version

        try:
            return version("butterpdf")
        except PackageNotFoundError:
            pass
    except ImportError:
        pass
    return "0.0.0+unknown"


__version__ = _resolve_version()

# Curated public API. configure() is eager — it must be callable before anything
# heavy imports (see butterpdf.identity: the font-scale loader reads QSettings at
# import time). The rest resolve LAZILY via __getattr__ so `import butterpdf` stays
# light: importing the chrome (window / app / design_tokens) would trip that
# import-time read before a fork's configure() could run. Reach for them
# (butterpdf.run_app, butterpdf.AppWindow, …) AFTER configuring.
_LAZY = {
    "run_app": ("butterpdf.app", "run_app"),
    "AppWindow": ("butterpdf.window", "AppWindow"),
    "AppBus": ("butterpdf.bus", "AppBus"),
    "get_bus": ("butterpdf.bus", "get_bus"),
    "Settings": ("butterpdf.settings", "Settings"),
    "get_settings": ("butterpdf.settings", "get_settings"),
}

__all__ = ["__version__", "configure", *_LAZY]


def __getattr__(name: str):
    target = _LAZY.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    import importlib

    return getattr(importlib.import_module(target[0]), target[1])
