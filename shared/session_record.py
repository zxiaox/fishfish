"""Creation and appending of opt-in Three Doors text records."""
from pathlib import Path


def create_game_records(path, door_layout, header):
    """Create separate session and pre-game layout files without overwriting."""
    path = Path(path)
    layout_path = path.with_name(path.stem + '-doors.txt')
    layout_created = False
    with path.open('x', encoding='utf-8', newline='\n') as session:
        try:
            with layout_path.open('x', encoding='utf-8', newline='\n') as layout:
                layout_created = True
                layout.write(door_layout)
            session.write(header)
        except Exception:
            # Close first on Windows; caller receives the original error.
            session.close()
            path.unlink(missing_ok=True)
            if layout_created: layout_path.unlink(missing_ok=True)
            raise
    return layout_path


def append_round(path, text):
    with Path(path).open('a', encoding='utf-8', newline='\n') as session:
        session.write(text + '\n')
