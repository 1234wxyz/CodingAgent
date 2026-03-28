from datetime import date, timedelta


def next_weekday(d: date, weekday: int) -> date:
    """Return the next date that falls on `weekday` (0=Monday ... 6=Sunday).

    If `d` is already that weekday, return the NEXT week's occurrence (not `d` itself).
    """
    days_ahead = weekday - d.weekday()
    if days_ahead < 0:
        days_ahead += 7
    return d + timedelta(days=days_ahead)
