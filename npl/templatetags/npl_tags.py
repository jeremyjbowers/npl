from django import template
from decimal import Decimal

register = template.Library()


@register.filter(name="kill_leading_zero")
def kill_leading_zero(value):
    if isinstance(value, Decimal):
        return str(value).replace("0.", ".")

    if isinstance(value, float):
        return str(value).replace("0.", ".")

    if isinstance(value, str):
        return value.replace("0.", ".")

    return value


@register.filter(name="commafy")
def commafy(n):
    r = []
    for i, c in enumerate(reversed(str(n))):
        if i and (not (i % 3)):
            r.insert(0, ",")
        r.insert(0, c)
    return "".join(r)


@register.filter()
def smooth_timedelta(timedeltaobj):
    """Convert a datetime.timedelta object into Days, Hours, Minutes, Seconds."""
    secs = timedeltaobj.total_seconds()
    timetot = ""
    if secs > 86400: # 60sec * 60min * 24hrs
        days = secs // 86400
        timetot += "{} days".format(int(days))
        secs = secs - days*86400

    if secs > 3600:
        hrs = secs // 3600
        timetot += " {} hours".format(int(hrs))
        secs = secs - hrs*3600

    if secs > 60:
        mins = secs // 60
        timetot += " {} minutes".format(int(mins))
        secs = secs - mins*60

    if secs > 0:
        timetot += " and {} seconds".format(int(secs))
    return timetot

