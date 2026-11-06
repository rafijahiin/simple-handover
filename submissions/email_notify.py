"""Email-based submission notifications — replaces Telegram per user request.

Sends transactional emails to focal-person addresses when:
  - A new field submission arrives (alerts the manager queue)
  - A manager approves a submission (confirms to the field worker)
  - A manager rejects a submission (lets the worker know why)
  - A 74-hour silence gap is detected (escalation to org lead)

All functions silently no-op if EMAIL_HOST is unset OR there are no
recipients with email addresses for the partner — the same defensive
pattern telegram.py uses.

Bilingual: subject lines stay English (for inbox scanning), but the
body carries both English and Bangla copies separated by a divider.
"""
import logging

from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone

logger = logging.getLogger(__name__)

DIVIDER = '\n\n────────────────\n\n'


def _submitter_email(submission) -> str:
    """Best-effort email of the person who filled the form, read from the
    Kobo payload. The form must carry an email question — common field names
    are accepted. Empty string when the form didn't collect one."""
    rd = getattr(submission, 'raw_data', None) or {}
    for key in ('email', 'submitter_email', 'your_email', 'respondent_email',
                'collector_email', 'reporter_email', 'contact_email'):
        val = str(rd.get(key, '') or '').strip()
        if '@' in val:
            return val
    return ''


def _recipients_for(partner: str) -> list[str]:
    """Find all email addresses for managers/supervisors/org_leads who should
    be notified about events for this partner. Supervisors + developers always
    get everything; focal/manager/org_lead only get their own partner."""
    from accounts.models import User
    qs = User.objects.filter(is_active=True).exclude(email='')
    cross_org = qs.filter(role__in=('supervisor', 'developer'))
    own_org = qs.filter(
        role__in=('focal', 'manager', 'org_lead'),
        organisation=partner,
    )
    return list({u.email for u in list(cross_org) + list(own_org)})


def _send(subject: str, body: str, recipients: list[str]) -> None:
    if not recipients:
        logger.info('email_notify: no recipients for "%s"', subject)
        return
    try:
        send_mail(
            subject=subject,
            message=body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=recipients,
            fail_silently=False,
        )
    except Exception as exc:
        # Don't propagate — a failing SMTP must never block submission ingest
        # or the manager-approval workflow.
        logger.error('email_notify failed for "%s": %s', subject, exc)


def send_submission_alert(submission) -> None:
    """A new submission has arrived. Tell the partner's manager queue."""
    recipients = _recipients_for(submission.partner)
    if not recipients:
        return
    subject = f'[SIMPLE] New {submission.get_form_type_display()} submission — {submission.partner}'
    body = (
        f'A new field submission is awaiting review.\n\n'
        f'Form:      {submission.get_form_type_display()}\n'
        f'Partner:   {submission.partner}\n'
        f'Worker:    {submission.worker_name or "—"}\n'
        f'District:  {submission.district or "—"}\n'
        f'Submitted: {submission.submitted_at:%d %b %Y %H:%M} UTC\n\n'
        f'Open SIMPLE to review and approve:\n{settings.SIMPLE_PUBLIC_URL}/approvals'
        + DIVIDER +
        f'একটি নতুন ফিল্ড জমা পর্যালোচনার জন্য অপেক্ষা করছে।\n'
        f'অনুমোদন করতে SIMPLE-এ লগইন করুন।'
    )
    _send(subject, body, recipients)


def send_approval_confirmation(submission) -> None:
    """Submission approved by manager — confirm to whoever submitted it."""
    recipients = _recipients_for(submission.partner)
    # Notify the field worker directly if the form captured their email.
    submitter = _submitter_email(submission)
    if submitter and submitter not in recipients:
        recipients = recipients + [submitter]
    if not recipients:
        return
    reviewer = getattr(submission.reviewed_by, 'full_name', None) or 'Manager'
    when = submission.reviewed_at or timezone.now()
    subject = f'[SIMPLE] ✓ {submission.get_form_type_display()} approved — {submission.partner}'
    body = (
        f'Your submission has been approved.\n\n'
        f'Form:        {submission.get_form_type_display()}\n'
        f'Worker:      {submission.worker_name or "—"}\n'
        f'District:    {submission.district or "—"}\n'
        f'Approved by: {reviewer}\n'
        f'Approved at: {when:%d %b %Y %H:%M} UTC'
        + DIVIDER +
        f'আপনার জমা অনুমোদিত হয়েছে। অনুমোদন করেছেন: {reviewer}।'
    )
    _send(subject, body, recipients)


def send_rejection_notification(submission) -> None:
    """Submission rejected — tell the worker so they can re-submit."""
    recipients = _recipients_for(submission.partner)
    # Send the rejection (with note + resubmit link) straight to the field
    # worker too, if the form captured their email.
    submitter = _submitter_email(submission)
    if submitter and submitter not in recipients:
        recipients = recipients + [submitter]
    if not recipients:
        return
    reviewer = getattr(submission.reviewed_by, 'full_name', None) or 'Manager'
    reason = submission.rejection_reason or 'No reason provided'
    from .form_links import resubmit_url
    link = resubmit_url(submission)
    link_line = f'\nResubmit here: {link}\n' if link else ''
    subject = f'[SIMPLE] ✗ {submission.get_form_type_display()} rejected — {submission.partner}'
    body = (
        f'Your submission was rejected and needs a corrected re-submission.\n\n'
        f'Form:        {submission.get_form_type_display()}\n'
        f'Worker:      {submission.worker_name or "—"}\n'
        f'Rejected by: {reviewer}\n'
        f'Reviewer note: {reason}\n'
        f'{link_line}\n'
        f'Please open the form again, fix the flagged field, and submit a '
        f'corrected entry. The rejected record is kept as an audit trail.'
        + DIVIDER +
        f'আপনার জমা প্রত্যাখ্যাত হয়েছে।\n'
        f'রিভিউয়ার নোট: {reason}\n'
        f'{link_line}'
        f'অনুগ্রহ করে ফর্মটি আবার খুলে সংশোধন করে জমা দিন।'
    )
    _send(subject, body, recipients)


def send_gap_alert(partner: str, hours_silent: float, threshold_hours: int) -> None:
    """No submissions in the threshold window — escalate to managers."""
    recipients = _recipients_for(partner)
    if not recipients:
        return
    subject = f'[SIMPLE] ⚠ {partner} silent for {hours_silent:.0f}h — please chase'
    body = (
        f'{partner} has not submitted any field data in the last '
        f'{hours_silent:.0f} hours.\n\n'
        f'Threshold: {threshold_hours} hours\n\n'
        f'Field staff are expected to submit at least once every '
        f'{threshold_hours} hours — even a zero-day return. Please chase '
        f'the focal person.\n\n'
        f'{settings.SIMPLE_PUBLIC_URL}/'
        + DIVIDER +
        f'{partner} গত {hours_silent:.0f} ঘণ্টায় কোনো ফিল্ড ডেটা জমা দেয়নি।\n'
        f'অনুগ্রহ করে ফোকাল ব্যক্তির সাথে যোগাযোগ করুন।'
    )
    _send(subject, body, recipients)


def send_gps_rejection_notice(worker_name: str, form_type: str) -> None:
    """GPS missing on a webhook submission — let managers know."""
    from accounts.models import User
    recipients = list(
        User.objects.filter(
            role__in=('manager', 'supervisor', 'org_lead'),
            is_active=True,
        ).exclude(email='').values_list('email', flat=True)
    )
    if not recipients:
        return
    form_label = form_type.replace('_', ' ').title()
    subject = f'[SIMPLE] ⚠ Submission rejected — GPS missing ({worker_name})'
    body = (
        f'A field submission was rejected because location (GPS) data was '
        f'not captured.\n\n'
        f'Worker: {worker_name}\n'
        f'Form:   {form_label}\n\n'
        f'Please remind the worker to enable phone GPS before submitting.'
        + DIVIDER +
        f'অবস্থান (GPS) তথ্য পাওয়া যায়নি বলে এই জমাটি বাতিল হয়েছে।\n'
        f'ফোনে লোকেশন চালু করে আবার জমা দিতে বলুন।'
    )
    _send(subject, body, recipients)
