import pytest
from PIL import Image

import portfolio.vision as vision_mod
from portfolio.extract import ExtractedImage
from portfolio.vision import ImageCaption, analyze_images


@pytest.fixture(autouse=True)
def _clear_vision_cache():
    """The module-level TTLCache in vision.py persists for the process's
    lifetime by design (it survives across /portfolio runs); tests must
    reset it so one test's cached caption can't leak into another's."""
    vision_mod._cache._store.clear()
    yield
    vision_mod._cache._store.clear()


def _img(color=(1, 2, 3)):
    return ExtractedImage(filename="x.png", image=Image.new("RGB", (4, 4), color), source="upload")


class _FakeStructuredLLM:
    def __init__(self, response=None, exc=None):
        self.response = response
        self.exc = exc
        self.calls = 0

    def invoke(self, messages):
        self.calls += 1
        if self.exc:
            raise self.exc
        return self.response


class _FakeLLM:
    def __init__(self, structured):
        self._structured = structured

    def with_structured_output(self, schema):
        return self._structured


def test_analyze_images_returns_caption_per_filename(monkeypatch):
    fake = _FakeStructuredLLM(response=ImageCaption(caption="A robot", alt_text="robot"))
    monkeypatch.setattr(vision_mod, "get_portfolio_llm", lambda: _FakeLLM(fake))
    results = analyze_images([_img()])
    assert results["x.png"].caption == "A robot"


def test_analyze_images_empty_list_short_circuits(monkeypatch):
    called = {"n": 0}
    monkeypatch.setattr(vision_mod, "get_portfolio_llm", lambda: called.__setitem__("n", called["n"] + 1))
    assert analyze_images([]) == {}
    assert called["n"] == 0


def test_failed_analysis_is_omitted_not_raised(monkeypatch):
    fake = _FakeStructuredLLM(exc=RuntimeError("boom"))
    monkeypatch.setattr(vision_mod, "get_portfolio_llm", lambda: _FakeLLM(fake))
    results = analyze_images([_img()])
    assert results == {}


def test_identical_image_content_is_served_from_cache(monkeypatch):
    fake = _FakeStructuredLLM(response=ImageCaption(caption="Cached", alt_text="c"))
    monkeypatch.setattr(vision_mod, "get_portfolio_llm", lambda: _FakeLLM(fake))
    same_content_twice = [
        ExtractedImage(filename="first.png", image=Image.new("RGB", (4, 4), (9, 9, 9)), source="upload"),
        ExtractedImage(filename="second.png", image=Image.new("RGB", (4, 4), (9, 9, 9)), source="upload"),
    ]
    results = analyze_images(same_content_twice)
    assert results["first.png"].caption == "Cached"
    assert results["second.png"].caption == "Cached"
    assert fake.calls == 1


@pytest.mark.parametrize("color_a,color_b", [((1, 1, 1), (2, 2, 2))])
def test_different_images_are_not_conflated_by_cache(monkeypatch, color_a, color_b):
    calls = []

    class _MultiResponseLLM:
        def with_structured_output(self, schema):
            return self

        def invoke(self, messages):
            calls.append(1)
            return ImageCaption(caption=f"call-{len(calls)}", alt_text="x")

    monkeypatch.setattr(vision_mod, "get_portfolio_llm", lambda: _MultiResponseLLM())
    images = [
        ExtractedImage(filename="a.png", image=Image.new("RGB", (4, 4), color_a), source="upload"),
        ExtractedImage(filename="b.png", image=Image.new("RGB", (4, 4), color_b), source="upload"),
    ]
    results = analyze_images(images)
    assert results["a.png"].caption != results["b.png"].caption
