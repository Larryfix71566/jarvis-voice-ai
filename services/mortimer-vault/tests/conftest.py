import os
import shutil
import tempfile

import pytest

from mortimer_vault.config import Paths
from mortimer_vault.index import Index
from mortimer_vault.vault import Vault


@pytest.fixture
def home(tmp_path, monkeypatch):
    h = tmp_path / "MortimerHome"
    monkeypatch.setenv("MORTIMER_HOME", str(h))
    return h


@pytest.fixture
def paths(home):
    p = Paths.build(home)
    p.ensure_layout("local")
    return p


@pytest.fixture
def vault(paths):
    return Vault(paths, "local")


@pytest.fixture
def index(paths):
    idx = Index(paths, "local")
    yield idx
    idx.close()
