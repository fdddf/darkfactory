"""The black box.

Explicitly not our deliverable. The point of this package is that it is
swappable: every implementation satisfies the same three-argument contract
and the confidence layer never looks inside.

    fix(bug, failing_test, repo) -> Patch
"""

from .fixture import FixtureFixer
from .devin import DevinFixer
from .tokenfactory import TokenFactoryFixer

__all__ = ["FixtureFixer", "DevinFixer", "TokenFactoryFixer", "get"]

_REGISTRY = {
    "fixture": FixtureFixer,
    "devin": DevinFixer,
    "tokenfactory": TokenFactoryFixer,
}


def get(name: str, **kwargs):
    if name not in _REGISTRY:
        raise SystemExit(f"unknown fixer '{name}'; have {', '.join(_REGISTRY)}")
    return _REGISTRY[name](**kwargs)
