from src.core.classification import Classification, classify_offer
from src.core.dedup import MatchResult, find_existing_offer
from src.core.normalization import NormalizedOffer, canonicalize_url, normalize_raw_offer, normalize_text

__all__ = [
    "Classification",
    "MatchResult",
    "NormalizedOffer",
    "canonicalize_url",
    "classify_offer",
    "find_existing_offer",
    "normalize_raw_offer",
    "normalize_text",
]
