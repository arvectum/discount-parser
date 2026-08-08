from __future__ import annotations

from pathlib import Path

from src.shared.config import get_settings

ENV_PATH = Path('.env')
ENV_EXAMPLE_PATH = Path('.env.example')

REQUIRED_TELEGRAM_KEYS = {
    'DP_TELEGRAM_BOT_TOKEN',
    'DP_TELEGRAM_CHANNEL_ID',
    'DP_TELEGRAM_ADMIN_IDS',
}


def _read_env(path: Path = ENV_PATH) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding='utf-8').splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith('#') or '=' not in stripped:
            continue
        key, value = stripped.split('=', 1)
        values[key.strip()] = value.strip()
    return values


def is_setup_complete() -> bool:
    values = _read_env()
    return all(values.get(key) for key in REQUIRED_TELEGRAM_KEYS)


def save_telegram_setup(
    *,
    bot_token: str,
    bot_name: str,
    channel_id: str,
    admin_ids: str,
) -> None:
    bot_token = bot_token.strip()
    bot_name = bot_name.strip()
    channel_id = channel_id.strip()
    admin_ids = admin_ids.strip()

    if ':' not in bot_token or len(bot_token) < 20:
        raise ValueError('Похоже, токен Telegram-бота указан неверно.')
    if not channel_id:
        raise ValueError('Укажите Telegram channel ID или @username канала.')
    if not admin_ids:
        raise ValueError('Укажите Telegram user ID администратора.')
    try:
        for value in admin_ids.split(','):
            int(value.strip())
    except ValueError as exc:
        raise ValueError('Telegram user ID должен быть числом. Несколько ID разделяйте запятыми.') from exc

    if ENV_PATH.exists():
        lines = ENV_PATH.read_text(encoding='utf-8').splitlines()
    elif ENV_EXAMPLE_PATH.exists():
        lines = ENV_EXAMPLE_PATH.read_text(encoding='utf-8').splitlines()
    else:
        lines = []

    replacements = {
        'DP_TELEGRAM_BOT_TOKEN': bot_token,
        'DP_TELEGRAM_BOT_NAME': bot_name,
        'DP_TELEGRAM_CHANNEL_ID': channel_id,
        'DP_TELEGRAM_ADMIN_IDS': admin_ids,
    }
    seen: set[str] = set()
    output: list[str] = []
    for line in lines:
        if '=' not in line or line.lstrip().startswith('#'):
            output.append(line)
            continue
        key = line.split('=', 1)[0].strip()
        if key in replacements:
            output.append(f'{key}={replacements[key]}')
            seen.add(key)
        else:
            output.append(line)
    for key, value in replacements.items():
        if key not in seen:
            output.append(f'{key}={value}')

    ENV_PATH.write_text('\n'.join(output).rstrip() + '\n', encoding='utf-8')
    get_settings.cache_clear()
