"""
CIPRB handover: prune partner (PHD / Bandhu) data from a database copy.

This command is for the GitHub + domain handover to CIPRB. It takes a FULL
restore of the production database (restored into a SCRATCH database on the
developer's side, never run against live production) and deletes everything that
belongs to the implementing partners, leaving a CIPRB-only database that is then
dumped and handed to CIPRB. Partner PII therefore never reaches CIPRB
infrastructure.

Buckets (every model in the project apps is classified; a completeness guard
aborts if any model is left unclassified):

  GO        keep entirely  - mpdsr, fistula, baseline, training, partners.Partner
  STAY      delete entirely - all programs service-delivery models,
                              programs.Client, pharmacy.PrescriptionRecord
  FILTER    keep CIPRB-relevant subset - accounts.User, programs.ServiceCenter,
                              submissions.KoboSubmission, indicators.* (by partner)
  REGEN     delete all rows (regenerated fresh on the new instance) -
                              reports.Report, tracker.Alert, tracker.MonthlyTarget,
                              programs.KoboSyncRun, programs.KoboWithdrawal

Safety: dry run by default (rolls back). --apply requires --yes-i-have-a-backup.
Encryption is untouched: rows move verbatim, so the FERNET_KEY is carried to the
new instance and rotated there afterwards (MultiFernet runbook in the handover
pack). This command never decrypts anything.
"""
from django.apps import apps
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import ForeignKey, OneToOneField
from django.db.models.deletion import ProtectedError

# Project apps whose data is in scope. Anything here must land in exactly one
# bucket below, or the completeness guard aborts.
PROJECT_APPS = {
    'accounts', 'programs', 'mpdsr', 'fistula', 'baseline', 'submissions',
    'indicators', 'reports', 'tracker', 'training', 'partners', 'pharmacy',
}

# GO: CIPRB's own data, kept in full.
KEEP_ENTIRE_APPS = {'mpdsr', 'fistula', 'baseline', 'training'}
KEEP_ENTIRE_MODELS = {'partners.Partner'}

# STAY: partner (PHD / Bandhu) service-delivery data, deleted in full.
# Order matters for PROTECT: service records -> Client -> (ServiceCenter handled
# in FILTER). pharmacy and GBVAccessLog/cost rows cascade or precede their parents.
DELETE_ENTIRE_MODELS = {
    'programs.ClinicVisit', 'programs.HIVSTITestResult', 'programs.ADRRecord',
    'programs.AntenatalCard', 'programs.AutoclaveLog', 'programs.HTCCounselling',
    'programs.IndividualCounselling', 'programs.MHScreening',
    'programs.PHDCounsellingReport', 'programs.GBVCase', 'programs.GBVAccessLog',
    'programs.GBVCornerRecord', 'programs.OutreachSession',
    'programs.GroupEducationSession', 'programs.WellnessLogbookEntry',
    'programs.MobileHealthCamp', 'programs.VisitorRegister',
    'programs.CoordMeeting', 'programs.TrainingEvent', 'programs.StockEntry',
    'programs.TemperatureLog', 'programs.SafetyHygieneKit',
    'programs.StoreRequisition', 'programs.Referral', 'programs.IECMaterial',
    'programs.NilReport', 'pharmacy.PrescriptionRecord',
}
# Deleted after the service records above (PROTECT-referenced by them).
DELETE_AFTER_SERVICES = ['programs.Client']

# REGEN: operational / generated, started fresh on the new instance.
REGEN_MODELS = {
    'reports.Report', 'tracker.Alert', 'tracker.MonthlyTarget',
    'programs.KoboSyncRun', 'programs.KoboWithdrawal',
}

# FILTER: kept CIPRB-relevant subset (handled explicitly in code).
FILTER_MODELS = {
    'accounts.User', 'programs.ServiceCenter', 'submissions.KoboSubmission',
}
# indicators.* models are filtered by a partner FK where present (keep CIPRB +
# shared/null), classified dynamically so new indicator models are caught.

KEEP_ORGS = {'CIPRB', 'UNFPA'}


def _label(model):
    return f'{model._meta.app_label}.{model._meta.object_name}'


def _fk_names_to(model, target_label):
    """Concrete FK/OneToOne field names on `model` pointing at `target_label`."""
    out = []
    for f in model._meta.get_fields():
        if isinstance(f, (ForeignKey, OneToOneField)) and f.concrete:
            if _label(f.related_model) == target_label:
                out.append(f.attname)  # e.g. 'submission_id', 'center_id'
    return out


class Command(BaseCommand):
    help = 'Prune PHD/Bandhu partner data from a CIPRB handover database copy.'

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true',
                            help='Actually delete. Without it, dry run (rolls back).')
        parser.add_argument('--yes-i-have-a-backup', action='store_true',
                            help='Required with --apply. Confirms this is a scratch copy.')

    def handle(self, *args, **opts):
        apply = opts['apply']
        if apply and not opts['yes_i_have_a_backup']:
            raise CommandError(
                '--apply requires --yes-i-have-a-backup. Run this ONLY on a '
                'scratch restore, never on live production.')

        indicator_models = [m for m in apps.get_app_config('indicators').get_models()]
        self._check_completeness(indicator_models)

        go_models = self._go_models()
        keep_submission_ids = self._referenced_ids(go_models, 'submissions.KoboSubmission')
        keep_center_ids = self._keep_center_ids(go_models)
        keep_user_ids = self._keep_user_ids(go_models, keep_submission_ids)

        self.stdout.write(self.style.MIGRATE_HEADING(
            '\nCIPRB handover prune  (%s)' % ('APPLY' if apply else 'DRY RUN')))
        self.stdout.write('  keep KoboSubmissions : %d' % len(keep_submission_ids))
        self.stdout.write('  keep ServiceCenters  : %d' % len(keep_center_ids))
        self.stdout.write('  keep Users           : %d\n' % len(keep_user_ids))

        rows = []
        try:
            with transaction.atomic():
                # 1. Partner service records (PROTECT-ref Client + ServiceCenter).
                for lbl in sorted(DELETE_ENTIRE_MODELS):
                    rows.append(self._delete_all(lbl))
                # 2. Partner Clients (PROTECT-ref ServiceCenter).
                for lbl in DELETE_AFTER_SERVICES:
                    rows.append(self._delete_all(lbl))
                # 3. Non-CIPRB ServiceCenters.
                rows.append(self._delete_filtered(
                    'programs.ServiceCenter', keep_center_ids))
                # 4. Operational / generated tables.
                for lbl in sorted(REGEN_MODELS):
                    rows.append(self._delete_all(lbl))
                # 5. indicators.* filtered by partner (keep CIPRB + shared).
                for m in indicator_models:
                    rows.append(self._delete_indicator(m))
                # 6. Partner KoboSubmission wrappers.
                rows.append(self._delete_filtered(
                    'submissions.KoboSubmission', keep_submission_ids))
                # 7. Partner user accounts (last; everything else SET_NULL or gone).
                rows.append(self._delete_filtered(
                    'accounts.User', keep_user_ids))

                if not apply:
                    transaction.set_rollback(True)
        except ProtectedError as exc:
            raise CommandError(
                'PROTECT blocked a delete (a kept row still references a '
                'deleted one). Nothing was committed. Detail: %s' % exc)

        self._report(rows, apply)

    # ----- classification ------------------------------------------------

    def _check_completeness(self, indicator_models):
        classified = set()
        classified |= KEEP_ENTIRE_MODELS | DELETE_ENTIRE_MODELS | REGEN_MODELS | FILTER_MODELS
        classified |= set(DELETE_AFTER_SERVICES)
        unclassified = []
        for cfg in apps.get_app_configs():
            if cfg.label not in PROJECT_APPS:
                continue
            for model in cfg.get_models():
                lbl = _label(model)
                if cfg.label in KEEP_ENTIRE_APPS:
                    continue
                if cfg.label == 'indicators':
                    continue  # all indicator models handled by _delete_indicator
                if lbl in classified:
                    continue
                unclassified.append(lbl)
        if unclassified:
            raise CommandError(
                'Unclassified models (add each to a bucket before running):\n  '
                + '\n  '.join(sorted(unclassified)))

    def _go_models(self):
        out = []
        for label in KEEP_ENTIRE_APPS:
            out.extend(apps.get_app_config(label).get_models())
        return out

    def _referenced_ids(self, models_, target_label):
        ids = set()
        for model in models_:
            for attn in _fk_names_to(model, target_label):
                ids |= set(
                    model._default_manager.exclude(**{attn: None})
                    .values_list(attn, flat=True))
        return ids

    def _keep_center_ids(self, go_models):
        Center = apps.get_model('programs', 'ServiceCenter')
        ids = set(Center.objects.filter(organisation='CIPRB')
                  .values_list('pk', flat=True))
        ids |= self._referenced_ids(go_models, 'programs.ServiceCenter')
        return ids

    def _keep_user_ids(self, go_models, keep_submission_ids):
        User = apps.get_model('accounts', 'User')
        ids = set(User.objects.filter(is_superuser=True).values_list('pk', flat=True))
        ids |= set(User.objects.filter(organisation__in=KEEP_ORGS)
                   .values_list('pk', flat=True))
        ids |= self._referenced_ids(go_models, 'accounts.User')
        Sub = apps.get_model('submissions', 'KoboSubmission')
        ids |= set(Sub.objects.filter(pk__in=keep_submission_ids)
                   .exclude(reviewed_by=None)
                   .values_list('reviewed_by_id', flat=True))
        return ids

    # ----- deletes -------------------------------------------------------

    def _delete_all(self, label):
        model = apps.get_model(*label.split('.'))
        qs = model._default_manager.all()
        before = qs.count()
        deleted = qs.delete()[0] if before else 0
        return (label, before, deleted, before - deleted)

    def _delete_filtered(self, label, keep_ids):
        model = apps.get_model(*label.split('.'))
        before = model._default_manager.count()
        qs = model._default_manager.exclude(pk__in=keep_ids)
        deleted = qs.delete()[0] if qs.exists() else 0
        return (label, before, deleted, before - deleted)

    def _delete_indicator(self, model):
        """Keep rows whose partner is CIPRB or unset; delete PHD/Bandhu rows.
        Models with no partner FK are kept entirely (shared config)."""
        label = _label(model)
        before = model._default_manager.count()
        partner_fk = _fk_names_to(model, 'partners.Partner')
        if not partner_fk:
            return (label + ' (config, kept)', before, 0, before)
        from django.db.models import Q
        attn = partner_fk[0]
        keep = Q(**{attn: None})
        Partner = apps.get_model('partners', 'Partner')
        ciprb = Partner.objects.filter(
            Q(code__iexact='CIPRB') | Q(name__icontains='CIPRB')
        ).values_list('pk', flat=True)
        keep |= Q(**{attn + '__in': list(ciprb)})
        qs = model._default_manager.exclude(keep)
        deleted = qs.delete()[0] if qs.exists() else 0
        return (label, before, deleted, before - deleted)

    def _report(self, rows, apply):
        self.stdout.write('\n  %-44s %8s %8s %8s' % ('model', 'before', 'deleted', 'kept'))
        self.stdout.write('  ' + '-' * 70)
        td = tk = 0
        for label, before, deleted, kept in rows:
            td += deleted
            tk += kept
            self.stdout.write('  %-44s %8d %8d %8d' % (label, before, deleted, kept))
        self.stdout.write('  ' + '-' * 70)
        self.stdout.write('  %-44s %8s %8d %8d' % ('TOTAL', '', td, tk))
        if apply:
            self.stdout.write(self.style.SUCCESS('\nApplied. Dump this database for CIPRB.'))
        else:
            self.stdout.write(self.style.WARNING(
                '\nDry run - rolled back, nothing changed. Re-run with '
                '--apply --yes-i-have-a-backup on a scratch copy.'))
