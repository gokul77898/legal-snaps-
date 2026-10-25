import json
from pathlib import Path

import httpx
import pytest
from PIL import Image

from app.pipeline import hf_ai
from app.schemas import InfographicContentPlan

pytestmark = pytest.mark.asyncio


class FakeSettings:
    hf_router_base_url = "https://router.test/v1"
    hf_provider_base_url = "https://router.test"
    hf_text_model = "Qwen/Qwen2.5-72B-Instruct"
    hf_image_model = "black-forest-labs/FLUX.1-dev"
    hf_image_provider = "fal-ai"

    def __init__(self, token: str = "hf_test_token"):
        self._token = token

    def get_effective_hf_token(self) -> str:
        return self._token


def install_transport(monkeypatch, handler):
    transport = httpx.MockTransport(handler)
    original = httpx.AsyncClient

    class PatchedClient(original):
        def __init__(self, *args, **kwargs):
            kwargs["transport"] = transport
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(hf_ai.httpx, "AsyncClient", PatchedClient)


def install_artwork_client(monkeypatch, image=None, error=None):
    seen = {}

    class FakeInferenceClient:
        def __init__(self, **kwargs):
            seen["init"] = kwargs

        async def text_to_image(self, prompt, **kwargs):
            seen["prompt"] = prompt
            seen["request"] = kwargs
            if error:
                raise RuntimeError(error)
            return image

    monkeypatch.setattr(hf_ai, "AsyncInferenceClient", FakeInferenceClient)
    return seen


def legal_record_payload(**overrides):
    data = {
        "article_title": "A v. B",
        "case_name": "A v. B",
        "holding_or_operative_order": "The impugned rule is struck down.",
        "material_facts": ["A fact stated in the judgment."],
        "exact_quotations": ["the rule is arbitrary"],
    }
    data.update(overrides)
    return data


def chat_body(content: str, finish_reason: str = "stop") -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "choices": [
                {
                    "message": {"role": "assistant", "content": content},
                    "finish_reason": finish_reason,
                }
            ]
        },
    )


def plan() -> InfographicContentPlan:
    return InfographicContentPlan(
        headline="Prisons and Caste",
        overview_text="A judgment about caste-based labour in prisons.",
        artwork_subject="prison bars with a weighing scale",
    )


async def test_missing_token_fails_before_any_network_call(monkeypatch):
    monkeypatch.setattr(hf_ai, "settings", FakeSettings(token=""))

    def explode(request):  # pragma: no cover - must never run
        raise AssertionError("network should not be touched without a token")

    install_transport(monkeypatch, explode)

    with pytest.raises(hf_ai.HFProviderError, match="HF_TOKEN"):
        await hf_ai.analyze_legal_with_hf("document text", "topic")


async def test_provider_rejection_propagates_instead_of_falling_back(monkeypatch):
    monkeypatch.setattr(hf_ai, "settings", FakeSettings())

    def handler(request):
        return httpx.Response(401, json={"error": "Invalid username or password."})

    install_transport(monkeypatch, handler)

    with pytest.raises(hf_ai.HFProviderError) as excinfo:
        await hf_ai.analyze_legal_with_hf("document text", "topic")

    message = str(excinfo.value)
    assert "401" in message
    assert "Invalid username or password" in message


async def test_valid_completion_is_schema_validated(monkeypatch):
    monkeypatch.setattr(hf_ai, "settings", FakeSettings())
    content = json.dumps(legal_record_payload())

    install_transport(monkeypatch, lambda request: chat_body(content))

    record = await hf_ai.analyze_legal_with_hf(
        "the rule is arbitrary because it lacks reasons", "topic", "https://example.org/doc"
    )

    assert record.case_name == "A v. B"
    assert record.holding_or_operative_order.startswith("The impugned rule")
    assert record.analysis_source == "huggingface:Qwen/Qwen2.5-72B-Instruct"


async def test_null_optional_lists_are_treated_as_empty(monkeypatch):
    monkeypatch.setattr(hf_ai, "settings", FakeSettings())
    content = json.dumps(
        legal_record_payload(bench_composition=None, relevant_statutes=None)
    )

    install_transport(monkeypatch, lambda request: chat_body(content))

    record = await hf_ai.analyze_legal_with_hf("document text", "topic")

    assert record.bench_composition == []
    assert record.relevant_statutes == []
    assert record.holding_or_operative_order.startswith("The impugned rule")


async def test_missing_holding_is_repaired_on_retry(monkeypatch):
    monkeypatch.setattr(hf_ai, "settings", FakeSettings())
    bad = legal_record_payload()
    bad.pop("holding_or_operative_order")
    good = legal_record_payload()
    calls = {"count": 0}

    def handler(request):
        calls["count"] += 1
        return chat_body(json.dumps(bad if calls["count"] == 1 else good))

    install_transport(monkeypatch, handler)

    record = await hf_ai.analyze_legal_with_hf("the rule is arbitrary", "topic")

    assert calls["count"] == 2
    assert record.holding_or_operative_order.startswith("The impugned rule")


async def test_completion_without_json_raises(monkeypatch):
    monkeypatch.setattr(hf_ai, "settings", FakeSettings())

    install_transport(monkeypatch, lambda request: chat_body("I cannot answer that."))

    with pytest.raises(hf_ai.HFProviderError, match="no JSON object"):
        await hf_ai.analyze_legal_with_hf("document text", "topic")


async def test_completion_failing_the_schema_raises(monkeypatch):
    monkeypatch.setattr(hf_ai, "settings", FakeSettings())
    content = json.dumps({"article_title": "A v. B"})

    install_transport(monkeypatch, lambda request: chat_body(content))

    with pytest.raises(hf_ai.HFProviderError, match="did not match the legal record schema"):
        await hf_ai.analyze_legal_with_hf("document text", "topic")


async def test_truncated_completion_raises(monkeypatch):
    monkeypatch.setattr(hf_ai, "settings", FakeSettings())

    install_transport(
        monkeypatch,
        lambda request: chat_body('{"article_title": "A v. B"', finish_reason="length"),
    )

    with pytest.raises(hf_ai.HFProviderError, match="token limit"):
        await hf_ai.analyze_legal_with_hf("document text", "topic")


async def test_paraphrased_quotation_is_removed_and_reported(monkeypatch):
    monkeypatch.setattr(hf_ai, "settings", FakeSettings())
    content = json.dumps(
        legal_record_payload(exact_quotations=["the rule is arbitrary"])
    )

    install_transport(monkeypatch, lambda request: chat_body(content))

    record = await hf_ai.analyze_legal_with_hf(
        "The rule is manifestly arbitrary, the Court held.", "topic"
    )

    assert record.exact_quotations == []
    assert any("Removed quotation" in note for note in record.uncertainties)


async def test_artwork_provider_error_returns_false(tmp_path, monkeypatch):
    monkeypatch.setattr(hf_ai, "settings", FakeSettings())
    install_artwork_client(monkeypatch, error="402 Insufficient credits")

    target = tmp_path / "art.png"
    ok, err = await hf_ai.generate_legal_artwork(str(target), plan())

    assert ok is False
    assert "402" in err and "Insufficient credits" in err
    assert not target.exists()


async def test_artwork_native_client_png_is_written(tmp_path, monkeypatch):
    monkeypatch.setattr(hf_ai, "settings", FakeSettings())
    image = Image.effect_noise((256, 256), 50).convert("RGB")
    seen = install_artwork_client(monkeypatch, image=image)

    target = tmp_path / "art.png"
    ok, err = await hf_ai.generate_legal_artwork(str(target), plan())

    assert ok is True, err
    payload = target.read_bytes()
    assert payload.startswith(b"\x89PNG\r\n\x1a\n")
    assert len(payload) > 2048
    assert seen["init"]["provider"] == "fal-ai"
    assert seen["init"]["api_key"] == "hf_test_token"
    assert seen["request"]["model"] == hf_ai.settings.hf_image_model
    assert seen["request"]["width"] == 1024
    assert seen["request"]["height"] == 1024
    assert "no text" in seen["prompt"].lower()
    assert "wig" in seen["request"]["negative_prompt"]


async def test_artwork_invalid_client_result_returns_false(tmp_path, monkeypatch):
    monkeypatch.setattr(hf_ai, "settings", FakeSettings())
    install_artwork_client(monkeypatch, image=None)

    target = tmp_path / "art.png"
    ok, err = await hf_ai.generate_legal_artwork(str(target), plan())

    assert ok is False
    assert "save" in err
    assert not target.exists()
