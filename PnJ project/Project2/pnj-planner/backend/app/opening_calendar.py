"""Regular gallery calendars, reviewed from the venue's own visitor information."""
import json
from datetime import date, timedelta
from pathlib import Path

CALENDAR = json.loads((Path(__file__).parent / "data/gallery_hours.json").read_text(encoding="utf-8"))


def opening_metadata(place_id):
    hours = CALENDAR["places"].get(place_id)
    if hours is None:
        return None
    return {**hours, "closed": CALENDAR["closure"], "checkedOn": CALENDAR["checkedOn"],
            "scope": CALENDAR["scope"], "lastAdmissionBeforeCloseMinutes": CALENDAR["lastAdmissionBeforeCloseMinutes"],
            "status": "published_regular_schedule"}


def regular_closure(place_id, start_date, day):
    if place_id not in CALENDAR["places"] or not start_date:
        return False
    first = date.fromisoformat(start_date) if isinstance(start_date, str) else start_date
    visit = first + timedelta(days=day - 1)
    closed = CALENDAR["closure"]
    return visit.weekday() in closed["weekday"] or visit.strftime("%m-%d") in closed["monthDay"]
