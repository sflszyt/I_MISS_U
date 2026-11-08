"""集中管理本机旧档案的账号标识；通用源码不保存个人标识。"""
import json
import os
from pathlib import Path
import re


def owner_participant(explicit=None, *, config_path=None):
    """优先级：显式值、进程环境、本机文件、中性默认值。"""
    value = explicit if explicit is not None else os.environ.get('IMISSU_OWNER_ID')
    if value is None:
        path = Path(config_path) if config_path is not None else Path(__file__).with_name('identity.local.json')
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding='utf-8'))
            except (ValueError, OSError):
                raise ValueError('Invalid local identity configuration') from None
            if not isinstance(data, dict) or set(data) != {'owner_participant'}:
                raise ValueError('Unsupported local identity configuration')
            value = data['owner_participant']
        else:
            value = 'owner'
    if (not isinstance(value, str) or not re.fullmatch(r'[a-z][a-z0-9_-]{0,63}', value)
            or value in {'mama', 'father', 'self'}
            or value.upper() in {'CON', 'PRN', 'AUX', 'NUL', *('COM' + str(i) for i in range(10)), *('LPT' + str(i) for i in range(10))}):
        raise ValueError('Invalid owner participant identifier')
    return value
