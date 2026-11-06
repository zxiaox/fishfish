"""Pure logic shared by platform-specific user interfaces."""
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
import random


def parse_time(value):
    for fmt in ('%H:%M', '%H:%M:%S'):
        try:
            return datetime.strptime(value.strip(), fmt).time()
        except ValueError:
            pass
    raise ValueError('time')


def work_interval(now, start, end):
    start, end = parse_time(start), parse_time(end)
    if start == end:
        raise ValueError('schedule')
    begin = datetime.combine(now.date(), start)
    finish = datetime.combine(now.date(), end)
    if end < start:
        finish += timedelta(days=1)
        if now.time() <= end:
            begin -= timedelta(days=1)
            finish -= timedelta(days=1)
    return begin, finish


def work_status(now, start, end, wage):
    begin, finish = work_interval(now, start, end)
    try:
        wage = Decimal(wage)
        if not wage.is_finite() or wage < 0:
            raise ValueError('wage')
    except (InvalidOperation, TypeError):
        raise ValueError('wage')
    total = (finish - begin).total_seconds()
    elapsed = max(0, min(total, (now - begin).total_seconds()))
    remaining = max(0, (finish - now).total_seconds())
    return remaining, Decimal(str(elapsed)) * wage / Decimal(3600), elapsed / total


def observed_work_by_day(previous, now, start, end, monotonic_elapsed):
    """Allocate observed work to calendar dates, including midnight boundaries."""
    if now <= previous or monotonic_elapsed <= 0:
        return {}
    wall_elapsed = (now - previous).total_seconds()
    # Never infer unobserved time while the system sleeps or the app is stalled.
    observed = min(monotonic_elapsed, wall_elapsed, 2.0)
    previous = max(previous, now - timedelta(seconds=observed))
    allocations = {}
    cursor = previous
    while cursor < now:
        boundary = datetime.combine(cursor.date() + timedelta(days=1), datetime.min.time())
        segment_end = min(now, boundary)
        # Consider shifts starting today and yesterday so a boundary inside a
        # segment cannot hide either side of a shift ending at midnight.
        seconds = 0.0
        start_time, end_time = parse_time(start), parse_time(end)
        if start_time == end_time:
            raise ValueError('schedule')
        for day in (cursor.date() - timedelta(days=1), cursor.date()):
            begin = datetime.combine(day, start_time)
            finish = datetime.combine(day, end_time)
            if end_time < start_time:
                finish += timedelta(days=1)
            seconds += max(0.0, (min(segment_end, finish) - max(cursor, begin)).total_seconds())
        if seconds:
            allocations[cursor.date().isoformat()] = seconds
        cursor = segment_end
    return allocations


def trial(strategy, rng=random):
    if strategy not in ('stay', 'switch'):
        raise ValueError('strategy')
    prize = rng.randrange(3)
    choice = rng.randrange(3)
    revealed = rng.choice([door for door in range(3) if door != choice and door != prize])
    final = choice if strategy == 'stay' else next(door for door in range(3) if door not in (choice, revealed))
    return {'prize': prize + 1, 'choice': choice + 1, 'revealed': revealed + 1, 'final': final + 1, 'strategy': strategy, 'won': final == prize}


def prepare_live_rounds(count, rng=random):
    if not 1 <= count <= 20:
        raise ValueError('round count')
    return [{'prize': rng.randrange(1, 4)} for _ in range(count)]


def choose_live_door(round_data, choice, rng=random):
    if type(choice) is not int or choice not in (1, 2, 3): raise ValueError('door')
    prize = round_data.get('prize')
    if type(prize) is not int or prize not in (1, 2, 3): raise ValueError('prize')
    revealed = rng.choice([door for door in (1, 2, 3) if door not in (prize, choice)])
    return {**round_data, 'choice': choice, 'revealed': revealed}


def finish_live_round(round_data, strategy):
    if strategy not in ('stay', 'switch'): raise ValueError('strategy')
    final = round_data['choice'] if strategy == 'stay' else next(d for d in (1, 2, 3) if d not in (round_data['choice'], round_data['revealed']))
    return {**round_data, 'final': final, 'strategy': strategy, 'won': final == round_data['prize']}
