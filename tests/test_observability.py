import asyncio

import litellm
import pytest
from agents import Agent, Runner
from agents.extensions.models.litellm_model import LitellmModel
from fastapi.testclient import TestClient
from litellm.types.utils import Choices, Message, ModelResponse, Usage
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from agent.agent import model_settings_for
from observability import instrument
from server import app as server_app
from tests.test_cli import hosted_exports  # noqa: F401  (shared tracing isolation fixture)


@pytest.fixture
def client(world):
    server_app._SESSIONS.clear()
    yield TestClient(server_app.app)
    server_app._SESSIONS.clear()


def test_create_session_rejects_a_role_that_differs_from_the_database(client):
    response = client.post("/sessions", json={"user_id": 1, "role": "support"})

    assert response.status_code == 403
    assert server_app._SESSIONS == {}


def test_a_token_for_one_session_cannot_authorize_another_session(client):
    first = client.post("/sessions", json={"user_id": 1, "role": "shopper"}).json()
    second = client.post("/sessions", json={"user_id": 9002, "role": "merchant"}).json()

    response = client.post(
        f"/sessions/{second['session_id']}/messages",
        headers={"Authorization": f"Bearer {first['token']}"},
        json={"message": "Show me order 4127."},
    )

    assert response.status_code == 403


def test_litellm_model_spans_record_token_usage(monkeypatch, hosted_exports):
    async def fake_acompletion(**kwargs):
        return ModelResponse(
            id="offline",
            model=kwargs["model"],
            choices=[Choices(index=0, finish_reason="stop", message=Message(role="assistant", content="hi"))],
            usage=Usage(prompt_tokens=123, completion_tokens=45, total_tokens=168),
        )

    monkeypatch.setattr(litellm, "acompletion", fake_acompletion)
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    try:
        instrument.instrument_genai(provider)
        model = LitellmModel(model="anthropic/claude-haiku-5-5")
        agent = Agent(name="usage", instructions="Say hi.", model=model, model_settings=model_settings_for(model))

        asyncio.run(Runner.run(agent, "hello"))

        generations = [s for s in exporter.get_finished_spans() if s.name == "openai.response"]
        assert len(generations) == 1
        assert generations[0].attributes["gen_ai.usage.input_tokens"] == 123
        assert generations[0].attributes["gen_ai.usage.output_tokens"] == 45
    finally:
        provider.shutdown()
