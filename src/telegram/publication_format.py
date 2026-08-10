from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import tempfile

from src.shared.runtime_paths import runtime_root


FIELD_DEFINITIONS: tuple[tuple[str, str], ...] = (
    ("merchant", "Поставщик"),
    ("price", "Цена"),
    ("discount", "Скидка"),
    ("cashback", "Кэшбэк"),
    ("delivery", "Доставка"),
    ("category", "Категория"),
    ("conditions", "Условия"),
    ("geo", "ГЕО"),
    ("valid_until", "Срок действия"),
    ("promo_code", "Промокод"),
)

DEFAULT_ORDER: tuple[str, ...] = tuple(key for key, _ in FIELD_DEFINITIONS)
DEFAULT_ENABLED: frozenset[str] = frozenset(DEFAULT_ORDER)
ALLOWED_FIELDS = frozenset(DEFAULT_ORDER)


@dataclass(frozen=True, slots=True)
class PublicationFormat:
    order: tuple[str, ...] = DEFAULT_ORDER
    enabled: frozenset[str] = DEFAULT_ENABLED

    def normalized(self) -> "PublicationFormat":
        seen: set[str] = set()
        order: list[str] = []
        for key in self.order:
            if key in ALLOWED_FIELDS and key not in seen:
                seen.add(key)
                order.append(key)
        for key in DEFAULT_ORDER:
            if key not in seen:
                order.append(key)
        enabled = frozenset(key for key in self.enabled if key in ALLOWED_FIELDS)
        return PublicationFormat(tuple(order), enabled)


def publication_format_path() -> Path:
    return runtime_root() / "telegram_publication_format.json"


def load_publication_format() -> PublicationFormat:
    path = publication_format_path()
    if not path.exists():
        return PublicationFormat()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        order = tuple(str(value) for value in data.get("order", []))
        enabled = frozenset(str(value) for value in data.get("enabled", []))
        return PublicationFormat(order=order, enabled=enabled).normalized()
    except (OSError, ValueError, TypeError):
        return PublicationFormat()


def save_publication_format(*, order: list[str], enabled: list[str]) -> PublicationFormat:
    value = PublicationFormat(tuple(order), frozenset(enabled)).normalized()
    path = publication_format_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(
        {"version": 1, "order": list(value.order), "enabled": sorted(value.enabled)},
        ensure_ascii=False,
        indent=2,
    ) + "\n"
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        handle.write(payload)
        tmp_path = Path(handle.name)
    tmp_path.replace(path)
    return value


def reset_publication_format() -> PublicationFormat:
    path = publication_format_path()
    try:
        path.unlink()
    except FileNotFoundError:
        pass
    return PublicationFormat()
