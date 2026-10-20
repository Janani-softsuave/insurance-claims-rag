from __future__ import annotations

# Loss-date-aware retrieval depends on every document in the corpus carrying an
# effective date range. Documents not listed here are treated as date-agnostic
# (effective across all time) via the sentinel range below, so a single `where`
# filter works uniformly for every chunk regardless of whether its source
# document was ever versioned. Chroma's $lte/$gte operators require numeric
# operands, so dates are stored as YYYYMMDD integers, not ISO strings.
DATE_AGNOSTIC_FROM = "1900-01-01"
DATE_AGNOSTIC_TO = "2999-12-31"


def date_to_int(iso_date: str) -> int:
    return int(iso_date.replace("-", ""))


DOCUMENT_METADATA: dict[str, dict] = {
    "exclusions_schedule_2023.md": {
        "endorsement_version": "2023-R1",
        "effective_from": "2023-01-01",
        "effective_to": "2024-12-31",
    },
    "exclusions_schedule_2025.md": {
        "endorsement_version": "2025-R1",
        "effective_from": "2025-01-01",
        "effective_to": DATE_AGNOSTIC_TO,
    },
}


def metadata_for(filename: str) -> dict:
    meta = DOCUMENT_METADATA.get(filename, {})
    effective_from = meta.get("effective_from", DATE_AGNOSTIC_FROM)
    effective_to = meta.get("effective_to", DATE_AGNOSTIC_TO)
    return {
        "endorsement_version": meta.get("endorsement_version", "base"),
        "effective_from": effective_from,
        "effective_to": effective_to,
        "effective_from_int": date_to_int(effective_from),
        "effective_to_int": date_to_int(effective_to),
    }
