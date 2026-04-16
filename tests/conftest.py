"""pytest 共享 fixtures."""

from __future__ import annotations

import pytest


@pytest.fixture
def lang() -> str:
    """默认语言 fixture."""
    return "zh"
