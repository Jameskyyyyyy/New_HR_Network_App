from __future__ import annotations

import random
from datetime import datetime, timedelta
from typing import Any


WEEKDAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def _parse_time(t: str) -> tuple[int, int]:
    """Parse HH:MM or HH:MM AM/PM to (hour, minute)."""
    t = t.strip().upper()
    if "AM" in t or "PM" in t:
        from datetime import datetime as _dt
        dt = _dt.strptime(t, "%I:%M %p")
        return dt.hour, dt.minute
    parts = t.split(":")
    return int(parts[0]), int(parts[1]) if len(parts) > 1 else 0


def calculate_send_times(
    count: int,
    allowed_days: list[str],
    window_start: str,
    window_end: str,
    daily_cap: int,
    interval_min: int,
    interval_max: int,
    start_from: datetime | None = None,
) -> list[datetime]:
    if not allowed_days:
        allowed_days = ["Mon", "Tue", "Wed", "Thu", "Fri"]

    start_h, start_m = _parse_time(window_start)
    end_h, end_m = _parse_time(window_end)

    now = start_from or datetime.utcnow()
    scheduled: list[datetime] = []
    current = now.replace(second=0, microsecond=0)

    day_counts: dict[str, int] = {}
    max_iterations = count * 20

    iterations = 0
    while len(scheduled) < count and iterations < max_iterations:
        iterations += 1
        day_name = WEEKDAY_NAMES[current.weekday()]

        if day_name not in allowed_days:
            current = current.replace(hour=start_h, minute=start_m) + timedelta(days=1)
            continue

        day_key = current.strftime("%Y-%m-%d")
        day_send_count = day_counts.get(day_key, 0)

        if day_send_count >= daily_cap:
            current = current.replace(hour=start_h, minute=start_m) + timedelta(days=1)
            continue

        if current.hour < start_h or (current.hour == start_h and current.minute < start_m):
            current = current.replace(hour=start_h, minute=start_m)

        window_end_dt = current.replace(hour=end_h, minute=end_m)
        if current >= window_end_dt:
            current = current.replace(hour=start_h, minute=start_m) + timedelta(days=1)
            continue

        scheduled.append(current)
        day_counts[day_key] = day_send_count + 1

        interval = random.randint(interval_min, interval_max)
        current = current + timedelta(minutes=interval)

    return scheduled
