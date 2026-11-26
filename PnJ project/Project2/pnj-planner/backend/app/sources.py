"""Offline feeds. A verified time window is required for every dated observation."""
from datetime import date, datetime

from . import survey_stats


def applicable(records, visit_date, place_ids):
    if not visit_date:
        return []
    result = []
    for record in records:
        if (record.get("placeId") not in place_ids or record.get("status") != "verified"
                or record.get("sourceType") not in {"official_static", "official_api", "measured_interest"}
                or not record.get("sourceUrl") or not record.get("usageTerms")):
            continue
        try:
            start = date.fromisoformat(record["validFrom"])
            end = date.fromisoformat(record["validThrough"])
            updated = datetime.fromisoformat(record["updatedAt"])
            retrieved = datetime.fromisoformat(record["retrievedAt"])
        except (ValueError, TypeError, KeyError):
            continue
        if updated.tzinfo and retrieved.tzinfo and updated <= retrieved and start <= visit_date <= end:
            result.append(record)
    return result


def external_context(visit_date, place_ids, *, event_records=(), trend_records=()):
    events = applicable(event_records, visit_date, place_ids)
    signals = applicable(trend_records, visit_date, place_ids)
    return {"events":{"status":"available" if events else "unconnected", "records":events},
            "trends":{"status":"available" if signals else "unconnected", "signals":signals or None}}


def availability():
    return {"planning":"offline_rules", "weather":"scenario_only",
            "statistics":{"status":"verified_historical_aggregate","id":survey_stats.DATA["id"]},
            "events":{"status":"unconnected"}, "trends":{"status":"unconnected"}, "liveRouting":False}
