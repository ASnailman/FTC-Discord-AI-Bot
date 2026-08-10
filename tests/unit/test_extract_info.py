import yaml
import pytest

from extraction import extract_info, extract_team_numbers, build_name_index

GOLDEN_PATH = "tests/fixtures/golden/extract_info_cases.yaml"


def _load_cases():
    with open(GOLDEN_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


CASES = _load_cases()


@pytest.fixture
def index(region_index_usil):
    return region_index_usil


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_extract_info_case(case, index):
    got = set(extract_team_numbers(case["question"], index))
    expected = set(case["expect"])
    forbidden = set(case["forbid"])

    missing = expected - got
    spurious = got & forbidden

    assert not missing, f"[{case['id']}] missing expected teams {missing}: got {got}"
    assert not spurious, f"[{case['id']}] matched forbidden teams {spurious}: got {got}"


def test_extract_info_meets_precision_recall_floor(index):
    """Aggregate precision/recall across the whole golden set. This is the
    ratchet: the floor only ever moves up as the extractor improves."""
    tp = fp = fn = 0
    for case in CASES:
        got = set(extract_team_numbers(case["question"], index))
        expected = set(case["expect"])
        tp += len(got & expected)
        fp += len(got - expected)
        fn += len(expected - got)

    precision = tp / (tp + fp) if (tp + fp) else 1.0
    recall = tp / (tp + fn) if (tp + fn) else 1.0

    assert precision >= 0.95, f"precision {precision:.3f} below floor"
    assert recall >= 0.90, f"recall {recall:.3f} below floor"


def test_extract_info_returns_provenance(index):
    results = extract_info("How many matches did 21333 win?", index)
    assert results == [(21333, "21333", "number")]


def test_extract_info_name_provenance(index):
    results = extract_info("tell me about Robo Knights", index)
    nums = {num for num, _, _ in results}
    assert nums == {9295, 16609}
    assert all(source == "name" for _, _, source in results)


def test_extract_info_caps_team_count():
    # 8 distinct single-token names, all above the length/stopword gate
    fake_index = {f"teamword{i}": i for i in range(8)}
    question = " ".join(fake_index.keys())
    results = extract_info(question, fake_index)
    assert len(results) <= 6


def test_extract_info_handles_none_index():
    assert extract_team_numbers("How many matches did 21333 win?", None) == [21333]


def test_extract_info_empty_question(index):
    assert extract_team_numbers("", index) == []


def test_build_name_index_dual_keys_for_multi_token_names():
    idx = build_name_index({"Robo Knights": 9295})
    assert idx["robo knights"] == {9295}
    assert idx["roboknights"] == {9295}


def test_build_name_index_single_token_name_not_split():
    idx = build_name_index({"RoboKnights": 33862})
    assert idx["roboknights"] == {33862}
    assert "robo knights" not in idx
