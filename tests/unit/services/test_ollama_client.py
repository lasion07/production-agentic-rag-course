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
