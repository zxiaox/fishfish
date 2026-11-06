"""Creation and appending of opt-in Three Doors text records."""
from pathlib import Path


def create_game_records(path, door_layout, header):
    """Write every committed prize layout before play and append results later."""
    path = Path(path)
    created = False
    try:
        with path.open('x', encoding='utf-8', newline='\n') as session:
            created = True
            session.write(header)
            session.write(door_layout)
    except FileExistsError:
        raise
    except Exception:
        if created: path.unlink(missing_ok=True)
        raise
    return path


def append_round(path, text):
    with Path(path).open('a', encoding='utf-8', newline='\n') as session:
        session.write(text + '\n')
