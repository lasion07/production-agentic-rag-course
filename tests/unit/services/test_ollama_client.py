from types import SimpleNamespace
from unittest.mock import patch

from src.services.ollama.client import OllamaClient


def test_generate_payload_places_runtime_controls_under_options():
    payload = OllamaClient._build_generate_payload(
        model="llama3.2:1b",
        prompt="question",
        stream=False,
        temperature=0.2,
        top_p=0.8,
        num_predict=128,
    )

    assert payload == {
        "model": "llama3.2:1b",
        "prompt": "question",
        "stream": False,
        "options": {"temperature": 0.2, "top_p": 0.8, "num_predict": 128},
    }


def test_generate_payload_keeps_format_at_top_level():
    schema = {"type": "object"}
    payload = OllamaClient._build_generate_payload(
        model="llama3.2:1b",
        prompt="question",
        stream=False,
        format=schema,
        temperature=0.1,
    )

    assert payload["format"] == schema
    assert payload["options"] == {"temperature": 0.1}


def test_langchain_adapter_inherits_runtime_connection_settings():
    settings = SimpleNamespace(ollama_host="http://ollama:11434", ollama_timeout=42)
    client = OllamaClient(settings)

    with patch("src.services.ollama.client.ChatOllama") as chat_ollama:
        model = client.get_langchain_model(model="model-b", temperature=0.25)

    assert model is chat_ollama.return_value
    kwargs = chat_ollama.call_args.kwargs
    assert kwargs["model"] == "model-b"
    assert kwargs["base_url"] == "http://ollama:11434"
    assert kwargs["temperature"] == 0.25
    assert kwargs["keep_alive"] == "10m"
    assert kwargs["async_client_kwargs"]["timeout"] is client.timeout
