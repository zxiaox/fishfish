"""Local-date and Chinese lunar-calendar presentation."""
from lunar_python import Solar


def calendar_lines(day, tr):
    """Return translated Gregorian date/weekday and Chinese lunar date."""
    gregorian = tr('calendar_date', date=day.isoformat(), weekday=tr('weekday_' + str(day.weekday())))
    try:
        lunar = Solar.fromYmd(day.year, day.month, day.day).getLunar()
        month = lunar.getMonth()
        text = tr('calendar_lunar', year=lunar.getYear(), month=abs(month), day=lunar.getDay(),
                  leap=tr('calendar_leap') if month < 0 else '')
    except (ValueError, ArithmeticError, OverflowError, IndexError):
        text = tr('calendar_lunar_unavailable')
    return gregorian, text
