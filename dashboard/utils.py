import datetime
from django.utils import timezone


def current_month_bounds() -> tuple[datetime.datetime, datetime.datetime]:
    """Returns (start_of_this_month, exclusive_start_of_next_month) as UTC datetimes."""
    now = timezone.now()
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if start.month == 12:
        end = start.replace(year=start.year + 1, month=1)
    else:
        end = start.replace(month=start.month + 1)
    return start, end


def previous_month_bounds() -> tuple[datetime.datetime, datetime.datetime]:
    start_this, _ = current_month_bounds()
    end = start_this
    start = (end - datetime.timedelta(days=1)).replace(
        day=1, hour=0, minute=0, second=0, microsecond=0
    )
    return start, end


def allowed_partners(user) -> list[str]:
    """Partners whose data this user is allowed to see.

    CIPRB is included for cross-org admins — it owns the MPDSR, Baseline and
    Fistula submissions, so omitting it hid CIPRB pending counts (e.g. the
    Approvals badge read 0 while the queue held a CIPRB MPDSR submission).

    CIPRB and UNFPA are the monitoring orgs: every staff member there (any
    role, including view-only focal persons) sees all partners' data, per
    the spec ("CIPRB and UNFPA have full access across all partner data").
    PHD/Bandhu users stay scoped to their own org."""
    if user.can_see_all_orgs or user.organisation in ('CIPRB', 'UNFPA'):
        return ['CIPRB', 'PHD', 'Bandhu']
    return [user.organisation]
