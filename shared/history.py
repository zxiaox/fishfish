"""Persistent experiment and live-game history for Three Doors."""
import json
from pathlib import Path

MAX_EXPERIMENTS = 50
MAX_LIVE_ROUNDS = 50


def load_history(path):
    try:
        data = json.loads(Path(path).read_text(encoding='utf-8'))
    except FileNotFoundError:
        return {'experiments': [], 'live_sessions': []}
    if not isinstance(data, dict) or not isinstance(data.get('experiments'), list) or not isinstance(data.get('live_sessions'), list):
        raise ValueError('Invalid history file')
    for entry in data['experiments']:
        if (not isinstance(entry, dict) or not isinstance(entry.get('date'), str) or
            entry.get('strategy') not in ('stay', 'switch') or
            any(type(entry.get(k)) is not int for k in ('trials', 'wins', 'losses')) or
            entry['trials'] <= 0 or entry['wins'] < 0 or entry['losses'] < 0 or
            entry['wins'] + entry['losses'] != entry['trials']):
            raise ValueError('Invalid experiment record')
    for session in data['live_sessions']:
        if not isinstance(session, dict) or not isinstance(session.get('date'), str) or not isinstance(session.get('rounds'), list):
            raise ValueError('Invalid live session')
        for record in session['rounds']:
            if (not isinstance(record, dict) or record.get('strategy') not in ('stay', 'switch') or
                type(record.get('won')) is not bool or
                any(type(record.get(k)) is not int or record[k] not in (1, 2, 3) for k in ('choice', 'revealed', 'final', 'prize'))):
                raise ValueError('Invalid live round')
    del data['experiments'][:-MAX_EXPERIMENTS]
    limit_live_rounds(data['live_sessions'])
    return data


def limit_live_rounds(sessions):
    total = sum(len(session['rounds']) for session in sessions)
    while sessions and total > MAX_LIVE_ROUNDS:
        excess = total - MAX_LIVE_ROUNDS
        rounds = sessions[0]['rounds']
        remove = min(excess, len(rounds))
        del rounds[:remove]; total -= remove
        if not rounds: sessions.pop(0)


def save_history(path, history):
    del history['experiments'][:-MAX_EXPERIMENTS]
    limit_live_rounds(history['live_sessions'])
    path = Path(path)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.replace(path)


def add_experiment(history, entry):
    history['experiments'].append(entry)
    del history['experiments'][:-MAX_EXPERIMENTS]
