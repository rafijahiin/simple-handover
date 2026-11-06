"""Audit trail for records removed because they were deleted in KoboToolbox.

A deletion that leaves no trace is indistinguishable from data loss. Every row
removed by programs.kobo_withdrawals is written here first, with a snapshot of
the record, so any figure that changes can be explained afterwards and, if the
deletion was a mistake, the record can be rebuilt from the snapshot.

This table is never written by the webhook or by a user; only the reconciliation
command writes it.
"""
from django.db import models

from ._base import TimestampedModel


class KoboWithdrawal(TimestampedModel):
    model_label = models.CharField(max_length=100, db_index=True)
    record_pk = models.CharField(max_length=64)
    kobo_submission_id = models.CharField(max_length=100, db_index=True)
    organisation = models.CharField(max_length=50, blank=True)
    # The approval state the record held when it was removed. A record that was
    # already APPROVED had been counted in reports, so its removal changes
    # published figures and needs to be findable later.
    approval_status = models.CharField(max_length=20, blank=True)
    snapshot = models.JSONField(default=dict, blank=True)
    actor = models.CharField(max_length=100, blank=True)
    # Why it was removed. Required when a person deletes from the approval
    # queue: without it the trail says a record vanished but not what was
    # wrong with it, which is the one thing anyone reading it later needs.
    reason = models.TextField(blank=True)

    class Meta:
        ordering = ('-created_at',)
        verbose_name = 'Kobo withdrawal'

    def __str__(self):
        return '%s %s (kobo %s)' % (self.model_label, self.record_pk,
                                    self.kobo_submission_id)


class KoboSyncRun(TimestampedModel):
    """One pass of the Kobo deletion sweep, successful or not.

    Persisted rather than held in memory because the web worker recycles every
    500 requests; without a row on disk the schedule would restart from zero
    each time and the sweep would run far more often than intended.
    """
    org = models.CharField(max_length=50, blank=True)
    applied = models.BooleanField(default=False)
    candidates = models.PositiveIntegerField(default=0)
    deleted = models.PositiveIntegerField(default=0)
    blocked = models.PositiveIntegerField(default=0)
    live_ids = models.PositiveIntegerField(default=0)
    # Empty when the pass completed. A pass that aborted on a partial read of
    # KoboToolbox stores why, so a run of failures is visible rather than
    # looking like a quiet period with nothing to delete.
    error = models.TextField(blank=True)
    # What this pass thought was missing. The next pass deletes only what is
    # missing again, so a read that skipped rows costs a delay and not data.
    candidate_ids = models.JSONField(default=list, blank=True)

    class Meta:
        ordering = ('-created_at',)
        verbose_name = 'Kobo sync run'

    def __str__(self):
        return '%s %s %s' % (self.created_at, self.org or 'all',
                             self.error or '%d deleted' % self.deleted)
