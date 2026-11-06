"""Clear D5 baseline DEMO data so live collection starts from a clean slate.

BASELINE ONLY. No other form type, model, partner or org is touched — the filter
is `form_type=FormType.BASELINE` plus the two baseline-only models.

Three things happen (all baseline-scoped):

1. DELETE the in-scope submissions + their BaselineResponse rows.
     --scope demo : only seeded demo rows (kobo_id starts with DEMO-BL-)
     --scope all  : EVERY baseline submission + response row

2. SWEEP ORPHAN response rows. `BaselineResponse.submission` and
   `BaselineSurvey.submission` are OneToOneField(on_delete=models.SET_NULL), so
   deleting a KoboSubmission does NOT remove its response — it ORPHANS it
   (submission=NULL). The dashboard reads BaselineResponse, not the submissions,
   so orphans keep showing up as phantom interviews. They belong to no surviving
   submission, so they are always swept.

3. MATERIALISE any remaining PENDING baseline submission. Baseline no longer needs
   approval (it auto-approves at ingest), but rows that landed BEFORE that change
   are stuck PENDING with no approval UI left to clear them — they would never
   count. Flip them to APPROVED and create their BaselineResponse directly, with
   `on_submission_status_change` DISCONNECTED: that signal fans out telegram/email
   and Railway's boot has no outbound network, which stalls past the healthcheck.

Dry-run by default; pass --commit to actually write.

Prod's DB is reachable only from inside Railway, so this runs via the Dockerfile
boot gate FLUSH_BASELINE_DATA=demo|all (set → redeploy → verify → unset).
"""
from django.core.management.base import BaseCommand
from django.db.models.signals import post_save

from baseline.models import BaselineResponse, BaselineSurvey
from submissions.models import FormType, KoboSubmission, SubmissionStatus

PREFIX = 'DEMO-BL-'


class Command(BaseCommand):
    help = 'Delete baseline demo data, sweep orphan responses, materialise stuck-pending rows.'

    def add_arguments(self, parser):
        parser.add_argument('--scope', choices=['demo', 'all'], default='demo',
                            help="'demo' = DEMO-BL- rows only; 'all' = every baseline row.")
        parser.add_argument('--commit', action='store_true',
                            help='Actually write (default is a dry run).')
        parser.add_argument('--no-materialize', action='store_true',
                            help='Skip approving/materialising leftover PENDING rows.')

    def handle(self, *args, **opts):
        scope = opts['scope']
        base = KoboSubmission.objects.filter(form_type=FormType.BASELINE)
        demo = base.filter(kobo_id__startswith=PREFIX)
        nondemo = base.exclude(kobo_id__startswith=PREFIX)
        resp_all = BaselineResponse.objects.all()

        self.stdout.write('── Baseline data on this database ──')
        self.stdout.write(f'  KoboSubmission (BASELINE): {base.count()}  '
                          f'(demo {demo.count()} · non-demo {nondemo.count()})')
        self.stdout.write(f'  ... pending: {base.filter(status=SubmissionStatus.PENDING).count()}')
        self.stdout.write(f'  BaselineResponse rows    : {resp_all.count()}  '
                          f'(orphaned/submission=NULL: {resp_all.filter(submission__isnull=True).count()})')
        self.stdout.write(f'  BaselineSurvey rows      : {BaselineSurvey.objects.count()}')

        subs = demo if scope == 'demo' else base
        sub_ids = list(subs.values_list('id', flat=True))
        resp = resp_all if scope == 'all' else resp_all.filter(submission_id__in=sub_ids)

        n_orph_pre = resp_all.filter(submission__isnull=True).count()
        pend_keep = (base.exclude(id__in=sub_ids)
                         .filter(status=SubmissionStatus.PENDING).count())
        self.stdout.write(f'── scope={scope} ──')
        self.stdout.write(f'  delete {len(sub_ids)} submission(s) + {resp.count()} response row(s)')
        self.stdout.write(f'  sweep  {n_orph_pre} orphaned response row(s)')
        if not opts['no_materialize']:
            self.stdout.write(f'  materialise {pend_keep} leftover PENDING submission(s) → APPROVED')

        if not opts['commit']:
            self.stdout.write('Dry run — pass --commit to write.')
            return

        # 1) delete in-scope rows (responses first — SET_NULL would orphan them)
        surv_q = (BaselineSurvey.objects.all() if scope == 'all'
                  else BaselineSurvey.objects.filter(submission_id__in=sub_ids))
        n_surv = surv_q.count(); surv_q.delete()
        n_resp = resp.count(); resp.delete()
        n_sub = len(sub_ids)
        KoboSubmission.objects.filter(id__in=sub_ids).delete()
        self.stdout.write(f'Deleted {n_sub} submission(s), {n_resp} response row(s), '
                          f'{n_surv} legacy survey row(s).')

        # 2) sweep orphans (belong to no surviving submission)
        orph = BaselineResponse.objects.filter(submission__isnull=True)
        n_orph = orph.count(); orph.delete()
        self.stdout.write(f'Swept {n_orph} orphaned response row(s).')

        # 3) materialise leftover PENDING (baseline needs no approval)
        if not opts['no_materialize']:
            from submissions.signals import on_submission_status_change
            post_save.disconnect(on_submission_status_change, sender=KoboSubmission)
            try:
                pending = list(KoboSubmission.objects.filter(
                    form_type=FormType.BASELINE, status=SubmissionStatus.PENDING))
                made = 0
                for s in pending:
                    s.status = SubmissionStatus.APPROVED
                    s.save(update_fields=['status'])
                    try:
                        BaselineResponse.objects.get_or_create_from_submission(s)
                        made += 1
                    except Exception as exc:  # noqa: BLE001
                        self.stdout.write(f'  !! response failed for {s.kobo_id}: {exc}')
            finally:
                post_save.connect(on_submission_status_change, sender=KoboSubmission)
            self.stdout.write(f'Materialised {made}/{len(pending)} leftover PENDING submission(s).')

        left_sub = KoboSubmission.objects.filter(form_type=FormType.BASELINE).count()
        left_pend = KoboSubmission.objects.filter(
            form_type=FormType.BASELINE, status=SubmissionStatus.PENDING).count()
        left_resp = BaselineResponse.objects.count()
        self.stdout.write(f'Remaining baseline → submissions={left_sub} (pending={left_pend})  '
                          f'responses={left_resp}')
