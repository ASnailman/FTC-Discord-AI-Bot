import copy
import json
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


def _load(rel_path: str):
    with open(FIXTURES / rel_path, encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def payload_14469_2022():
    return copy.deepcopy(_load("ftcscout/team_14469_2022.json"))


@pytest.fixture
def payload_14469_2025():
    return copy.deepcopy(_load("ftcscout/team_14469_2025.json"))


@pytest.fixture
def payload_21333_2024():
    return copy.deepcopy(_load("ftcscout/team_21333_2024.json"))


@pytest.fixture
def payload_9295_2025():
    return copy.deepcopy(_load("ftcscout/team_9295_2025.json"))


@pytest.fixture
def payload_112_2022():
    return copy.deepcopy(_load("ftcscout/team_112_2022.json"))


@pytest.fixture
def payload_20266_2021_remote():
    return copy.deepcopy(_load("ftcscout/team_20266_2021.json"))


@pytest.fixture
def payload_9930_2025_sparse():
    return copy.deepcopy(_load("ftcscout/team_9930_2025_sparse.json"))


@pytest.fixture
def region_index_usil():
    return copy.deepcopy(_load("teams_index/USIL.json"))


@pytest.fixture
def hash_ef():
    from tests.support.embeddings import DeterministicHashEmbeddingFunction
    return DeterministicHashEmbeddingFunction()
