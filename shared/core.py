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


def work_status(now, start, end, wage):
    start, end = parse_time(start), parse_time(end)
    try:
        wage = Decimal(wage)
        if not wage.is_finite() or wage < 0:
            raise ValueError('wage')
    except (InvalidOperation, TypeError):
        raise ValueError('wage')
    begin = datetime.combine(now.date(), start)
    finish = datetime.combine(now.date(), end)
    if finish <= begin:
        raise ValueError('schedule')
    total = (finish - begin).total_seconds()
    elapsed = max(0, min(total, (now - begin).total_seconds()))
    remaining = max(0, (finish - now).total_seconds())
    return remaining, Decimal(str(elapsed)) * wage / Decimal(3600), elapsed / total


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
    rounds = []
    for _ in range(count):
        prize = rng.randrange(1, 4)
        choice = rng.randrange(1, 4)
        revealed = rng.choice([d for d in (1, 2, 3) if d not in (prize, choice)])
        rounds.append({'prize': prize, 'choice': choice, 'revealed': revealed})
    return rounds


def finish_live_round(round_data, strategy):
    if strategy not in ('stay', 'switch'): raise ValueError('strategy')
    final = round_data['choice'] if strategy == 'stay' else next(d for d in (1, 2, 3) if d not in (round_data['choice'], round_data['revealed']))
    return {**round_data, 'final': final, 'strategy': strategy, 'won': final == round_data['prize']}
