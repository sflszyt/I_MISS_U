"""Non-secret, fail-closed father OpenAI policy shared by builder and proxy."""
import json
from pathlib import Path

OPENAI_MODELS = ("gpt-6-luna", "gpt-6.1-terra", "gpt-6.1-sol")
DEFAULT_POLICY = Path(__file__).with_name("father_openai_policy.json")
CREDENTIAL_TARGET = "I_MISS_U/father/openai"


def validate_models(models):
    if (not isinstance(models, list) or any(not isinstance(m, str) or m not in OPENAI_MODELS for m in models)
            or len(set(models)) != len(models)):
        raise ValueError("invalid father OpenAI policy")
    return tuple(models)


def load_policy(path=None):
    try:
        data = json.loads(Path(path or DEFAULT_POLICY).read_text(encoding="utf-8"))
        if (not isinstance(data, dict) or set(data) != {"version", "enabled_models"}
                or type(data["version"]) is not int or data["version"] != 1):
            raise ValueError()
        return validate_models(data["enabled_models"])
    except (OSError, UnicodeError, ValueError, TypeError):
        raise ValueError("invalid father OpenAI policy") from None
