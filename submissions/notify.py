"""Facade that fans every notification out to both Telegram and Email.

Existing call sites import these names and stay unchanged. Each function
calls the matching telegram + email function defensively — failure in
one channel never blocks the other.
"""
from . import email_notify, telegram


def _safe(fn, *args, **kwargs):
    try:
        fn(*args, **kwargs)
    except Exception:
        # Channel-level failures are already logged inside each module.
        # Swallow so a broken SMTP can't take down a working Telegram path
        # (or vice versa).
        pass


def send_submission_alert(submission) -> None:
    _safe(telegram.send_submission_alert, submission)
    _safe(email_notify.send_submission_alert, submission)


def send_approval_confirmation(submission) -> None:
    _safe(telegram.send_approval_confirmation, submission)
    _safe(email_notify.send_approval_confirmation, submission)


def send_rejection_notification(submission) -> None:
    _safe(telegram.send_rejection_notification, submission)
    _safe(email_notify.send_rejection_notification, submission)


def send_gps_rejection_notice(worker_name: str, form_type: str) -> None:
    _safe(telegram.send_gps_rejection_notice, worker_name, form_type)
    _safe(email_notify.send_gps_rejection_notice, worker_name, form_type)


def send_gap_alert(partner: str, hours_silent: float, threshold_hours: int) -> None:
    # Telegram's older API only took (partner, form_type) and didn't carry
    # the silence-hours number. Email is the preferred channel for this.
    _safe(email_notify.send_gap_alert, partner, hours_silent, threshold_hours)
