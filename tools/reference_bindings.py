"""私有实验参考素材绑定；缺少绑定时拒绝运行，不降级为任意参考。"""
import json
import os
from pathlib import Path
import re


def load_reference_bindings(path=None):
    path = Path(path or os.environ.get('IMISSU_REFERENCE_BINDINGS') or
                Path(__file__).with_name('reference_bindings.local.json'))
    try:
        values = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        raise ValueError('Explicit private reference bindings are required') from None
    if (not isinstance(values, dict)
            or set(values) != {'REFERENCE_AUDIO', 'REFERENCE_TEXT', 'REFERENCE_SOURCE'}
            or any(not isinstance(value, str) or not re.fullmatch('[a-f0-9]{64}', value) for value in values.values())):
        raise ValueError('Invalid private reference bindings')
    return values
