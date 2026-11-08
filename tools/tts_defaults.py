"""Load optional machine-local TTS paths without publishing personal filenames."""
import json
from pathlib import Path


LOCAL_DEFAULT_KEYS = frozenset({
    'MODELS_DIR_DEFAULT', 'EXP_DIR_DEFAULT', 'REF_DEFAULT', 'PROMPT_TEXT_DEFAULT',
})


def load_local_defaults(path=None):
    path = Path(path) if path is not None else Path(__file__).with_name('tts_local_defaults.json')
    if not path.exists():
        return {}
    try:
        values = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        raise ValueError('Invalid local TTS defaults file') from None
    if (not isinstance(values, dict) or set(values) - LOCAL_DEFAULT_KEYS
            or any(not isinstance(value, str) or not value for value in values.values())):
        raise ValueError('Local TTS defaults must contain only supported nonempty path strings')
    return values
