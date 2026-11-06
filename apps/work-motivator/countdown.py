"""Countdown duration and deadline logic, independent of the user interface."""
import math
import re

DEFAULT_DURATION = '05:00:00'


def parse_duration(value):
    """Parse a positive duration in H:MM:SS format (up to 999 hours)."""
    if not isinstance(value, str): raise ValueError('duration')
    match = re.fullmatch(r'\s*(\d{1,3}):([0-5]\d):([0-5]\d)\s*', value)
    if not match: raise ValueError('duration')
    hours, minutes, seconds = map(int, match.groups())
    total = hours * 3600 + minutes * 60 + seconds
    if not total: raise ValueError('duration')
    return total


def new_deadline(enabled, duration, was_enabled, old_duration, deadline, now, reset=False):
    """Keep a running deadline unless the countdown is enabled, changed, or restarted."""
    seconds = parse_duration(duration)
    if not enabled: return None
    valid_deadline = isinstance(deadline, (int, float)) and not isinstance(deadline, bool) and math.isfinite(deadline)
    if reset or not was_enabled or duration != old_duration or not valid_deadline:
        return now + seconds
    return deadline


def remaining_text(deadline, now):
    seconds = max(0, math.ceil(deadline - now))
    hours, seconds = divmod(seconds, 3600)
    minutes, seconds = divmod(seconds, 60)
    return f'{hours:02}:{minutes:02}:{seconds:02}'
