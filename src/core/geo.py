from __future__ import annotations

from dataclasses import dataclass
import re


GEO_SCOPES = {"all_russia", "region", "city", "unknown"}


@dataclass(frozen=True, slots=True)
class GeoResult:
    city: str | None = None
    region: str | None = None
    scope: str = "unknown"


_CITY_ALIASES: tuple[tuple[str, str], ...] = (
    ("санкт-петербурге", "Санкт-Петербург"), ("санкт петербурге", "Санкт-Петербург"),
    ("санкт-петербург", "Санкт-Петербург"), ("санкт петербург", "Санкт-Петербург"),
    ("петербурге", "Санкт-Петербург"), ("спб", "Санкт-Петербург"),
    ("москве", "Москва"), ("москвы", "Москва"), ("москва", "Москва"),
    ("новосибирске", "Новосибирск"), ("новосибирск", "Новосибирск"),
    ("екатеринбурге", "Екатеринбург"), ("екатеринбург", "Екатеринбург"),
    ("казани", "Казань"), ("казань", "Казань"),
    ("нижнем новгороде", "Нижний Новгород"), ("нижний новгород", "Нижний Новгород"),
    ("челябинске", "Челябинск"), ("челябинск", "Челябинск"),
    ("самаре", "Самара"), ("самара", "Самара"), ("омске", "Омск"), ("омск", "Омск"),
    ("ростове-на-дону", "Ростов-на-Дону"), ("ростове на дону", "Ростов-на-Дону"),
    ("ростов-на-дону", "Ростов-на-Дону"), ("ростов на дону", "Ростов-на-Дону"),
    ("уфе", "Уфа"), ("уфа", "Уфа"), ("красноярске", "Красноярск"), ("красноярск", "Красноярск"),
    ("перми", "Пермь"), ("пермь", "Пермь"), ("воронеже", "Воронеж"), ("воронеж", "Воронеж"),
    ("волгограде", "Волгоград"), ("волгоград", "Волгоград"), ("краснодаре", "Краснодар"),
    ("краснодар", "Краснодар"), ("сочи", "Сочи"),
)

_REGION_ALIASES: tuple[tuple[str, str], ...] = (
    ("московской области", "Московская область"), ("московская область", "Московская область"),
    ("ленинградской области", "Ленинградская область"), ("ленинградская область", "Ленинградская область"),
    ("республике татарстан", "Республика Татарстан"), ("республика татарстан", "Республика Татарстан"),
    ("татарстане", "Республика Татарстан"), ("татарстан", "Республика Татарстан"),
    ("краснодарском крае", "Краснодарский край"), ("краснодарский край", "Краснодарский край"),
    ("красноярском крае", "Красноярский край"), ("красноярский край", "Красноярский край"),
    ("пермском крае", "Пермский край"), ("пермский край", "Пермский край"),
)

_ALL_RUSSIA_RE = re.compile(
    r"(?:по\s+всей\s+россии|вся\s+россия|в\s+любом\s+городе\s+россии|во\s+всех\s+городах\s+россии|"
    r"по\s+россии|на\s+территории\s+рф|по\s+всей\s+рф|федеральн\w*\s+акци\w*)",
    re.IGNORECASE,
)
_EXPLICIT_CITY_RE = re.compile(r"(?:\bг(?:ород)?\.?\s+)([А-ЯЁ][А-Яа-яЁё-]+(?:\s+[А-ЯЁ][А-Яа-яЁё-]+){0,2})", re.IGNORECASE)
_REGION_RE = re.compile(
    r"\b((?:Республик(?:а|е)\s+[А-ЯЁ][А-Яа-яЁё-]+)|(?:[А-ЯЁ][А-Яа-яЁё-]+(?:\s+[А-ЯЁ][А-Яа-яЁё-]+){0,2}\s+(?:область|области|край|крае|автономный\s+округ|автономном\s+округе|АО)))\b",
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


def extract_geo(
    *parts: str | None,
    city: str | None = None,
    region: str | None = None,
    scope: str | None = None,
) -> GeoResult:
    explicit_city = _clean(city) if city else None
    explicit_region = _clean(region) if region else None
    explicit_scope = (scope or "").strip().lower()
    if explicit_scope in GEO_SCOPES and explicit_scope != "unknown":
        return GeoResult(city=explicit_city or None, region=explicit_region or None, scope=explicit_scope)
    if explicit_city:
        return GeoResult(city=explicit_city, region=explicit_region or None, scope="city")
    if explicit_region:
        return GeoResult(region=explicit_region, scope="region")

    text = "\n".join(part for part in parts if part).strip()
    if not text:
        return GeoResult()
    if _ALL_RUSSIA_RE.search(text):
        return GeoResult(scope="all_russia")

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

    if detected_city:
        return GeoResult(city=detected_city, region=detected_region, scope="city")
    if detected_region:
        return GeoResult(region=detected_region, scope="region")
    return GeoResult()
