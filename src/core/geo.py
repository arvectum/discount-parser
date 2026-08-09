from __future__ import annotations

from dataclasses import dataclass
import re


@dataclass(frozen=True, slots=True)
class GeoResult:
    city: str | None = None
    region: str | None = None


_CITY_ALIASES: tuple[tuple[str, str], ...] = (
    ("санкт-петербург", "Санкт-Петербург"),
    ("санкт петербург", "Санкт-Петербург"),
    ("спб", "Санкт-Петербург"),
    ("москва", "Москва"),
    ("новосибирск", "Новосибирск"),
    ("екатеринбург", "Екатеринбург"),
    ("казань", "Казань"),
    ("нижний новгород", "Нижний Новгород"),
    ("челябинск", "Челябинск"),
    ("самара", "Самара"),
    ("омск", "Омск"),
    ("ростов-на-дону", "Ростов-на-Дону"),
    ("ростов на дону", "Ростов-на-Дону"),
    ("уфа", "Уфа"),
    ("красноярск", "Красноярск"),
    ("пермь", "Пермь"),
    ("воронеж", "Воронеж"),
    ("волгоград", "Волгоград"),
    ("краснодар", "Краснодар"),
    ("сочи", "Сочи"),
)

_REGION_ALIASES: tuple[tuple[str, str], ...] = (
    ("московская область", "Московская область"),
    ("ленинградская область", "Ленинградская область"),
    ("республика татарстан", "Республика Татарстан"),
    ("татарстан", "Республика Татарстан"),
    ("краснодарский край", "Краснодарский край"),
    ("красноярский край", "Красноярский край"),
    ("пермский край", "Пермский край"),
)

_EXPLICIT_CITY_RE = re.compile(
    r"(?:\bг(?:ород)?\.?\s+)([А-ЯЁ][А-Яа-яЁё-]+(?:\s+[А-ЯЁ][А-Яа-яЁё-]+){0,2})",
    re.IGNORECASE,
)
_REGION_RE = re.compile(
    r"\b((?:Республика\s+[А-ЯЁ][А-Яа-яЁё-]+)|(?:[А-ЯЁ][А-Яа-яЁё-]+(?:\s+[А-ЯЁ][А-Яа-яЁё-]+){0,2}\s+(?:область|край|автономный\s+округ|АО)))\b",
    re.IGNORECASE,
)


def _clean(value: str) -> str:
    return " ".join(value.replace("ё", "е").split()).strip(" ,.;:()[]")


def _canonical_from_aliases(text: str, aliases: tuple[tuple[str, str], ...]) -> str | None:
    lowered = text.casefold()
    for token, canonical in aliases:
        if re.search(rf"(?<![\w-]){re.escape(token)}(?![\w-])", lowered):
            return canonical
    return None


def extract_geo(*parts: str | None, city: str | None = None, region: str | None = None) -> GeoResult:
    explicit_city = _clean(city) if city else None
    explicit_region = _clean(region) if region else None
    if explicit_city or explicit_region:
        return GeoResult(city=explicit_city or None, region=explicit_region or None)

    text = "\n".join(part for part in parts if part).strip()
    if not text:
        return GeoResult()

    detected_region = _canonical_from_aliases(text, _REGION_ALIASES)
    if detected_region is None:
        match = _REGION_RE.search(text)
        if match:
            detected_region = _clean(match.group(1))

    detected_city = _canonical_from_aliases(text, _CITY_ALIASES)
    if detected_city is None:
        match = _EXPLICIT_CITY_RE.search(text)
        if match:
            detected_city = _clean(match.group(1))

    return GeoResult(city=detected_city, region=detected_region)
