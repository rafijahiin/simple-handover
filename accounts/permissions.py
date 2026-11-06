"""
Permission classes for the IDMS role taxonomy.

Two layers:

  1. Identity classes — `IsSupervisor`, `IsManager`, etc. — check one role.
     Use sparingly; prefer capability classes.

  2. Capability classes — `CanApproveSubmissions`, `CanConfigureTargets`,
     `CanWriteFieldRecord`, `CanWriteOutreach`, `CanAccessMPDSR` — encapsulate
     the rules in the User-model capability methods. Views should use these
     so the permission rules live in one place (the User model) and not
     scattered across ViewSets.

Backward-compat aliases (`IsSuperAdmin`, `IsSuperAdminOrManager`,
`IsSuperAdminOrDeveloper`) are kept so the migration to new roles can land
without touching every ViewSet at once. They will be removed in a follow-up
commit after every call site is migrated to the new classes.
"""
from rest_framework.permissions import BasePermission, SAFE_METHODS

from .models import Role, Organisation

# Monitoring orgs — CIPRB and UNFPA oversee the whole programme, so their
# staff (any role) get read-only visibility across all partners and into
# CIPRB-owned clinical aggregates. PHD/Bandhu remain scoped to their own org.
MONITORING_ORGS = (Organisation.CIPRB, Organisation.UNFPA)


# ── Identity classes ──────────────────────────────────────────────────────────

class _RoleIn(BasePermission):
    """Internal helper: subclass and set `roles` to a tuple of Role values."""
    roles: tuple = ()

    def has_permission(self, request, view):
        return (
            request.user.is_authenticated
            and request.user.role in self.roles
        )


class IsDeveloper(_RoleIn):
    roles = (Role.DEVELOPER,)


class IsSupervisor(_RoleIn):
    roles = (Role.SUPERVISOR,)


class IsOrgLead(_RoleIn):
    roles = (Role.ORG_LEAD,)


class IsManager(_RoleIn):
    """Manager only. For write actions, prefer CanWriteOutreach."""
    roles = (Role.MANAGER,)


class IsFieldStaff(_RoleIn):
    roles = (Role.FIELD_STAFF,)


class IsCIPRBBaseline(_RoleIn):
    roles = (Role.CIPRB_BASELINE,)


class IsFocal(_RoleIn):
    roles = (Role.FOCAL,)


# ── Capability classes (preferred) ────────────────────────────────────────────

class CanApproveSubmissions(BasePermission):
    """Approve/reject Kobo submissions. Manager+Org Lead+Supervisor+Developer."""
    def has_permission(self, request, view):
        u = request.user
        return u.is_authenticated and u.can_approve_submissions


class CanConfigureTargets(BasePermission):
    """
    Edit IndicatorTarget rows.

    UNFPA Supervisor + Developer (Rafi) only — org leads are NOT
    allowed to edit targets (Animesh's 2026-06-01 directive). For
    write actions, the partner being edited is taken from request
    body (`partner` field) or the URL/query. Falls back to
    instance.partner for detail actions.
    """
    def has_permission(self, request, view):
        u = request.user
        if not u.is_authenticated:
            return False
        if request.method in SAFE_METHODS:
            # Read access stays broad — anyone authenticated can list
            # / view their own org's targets via the queryset filter.
            return True
        # Determine partner from request data
        partner = (
            request.data.get('partner')
            if hasattr(request, 'data') else None
        ) or request.query_params.get('partner', '')
        # If not specified on a write, fall through to per-object check
        if not partner:
            return u.role in (Role.DEVELOPER, Role.SUPERVISOR)
        return u.can_configure_targets(partner)

    def has_object_permission(self, request, view, obj):
        u = request.user
        if request.method in SAFE_METHODS:
            return True
        # `obj.partner` may be a Partner FK instance (new IndicatorTarget
        # shape) or a raw string (legacy models). Normalise to the code.
        partner_obj = getattr(obj, 'partner', None)
        if partner_obj is None:
            partner_code = getattr(obj, 'organisation', '')
        elif hasattr(partner_obj, 'code'):
            partner_code = partner_obj.code
        else:
            partner_code = partner_obj   # already a string
        return u.can_configure_targets(partner_code)


class CanWriteFieldRecord(BasePermission):
    """
    Write access for FIELD records: HTC, HIV/STI, GBV, MH (depression/PTSD).

    These records originate from field staff via Kobo. Managers are
    EXPLICITLY excluded from write — managers approve, not enter.

    Read access is granted to all authenticated users (queryset filtering
    enforces org isolation downstream).
    """
    def has_permission(self, request, view):
        u = request.user
        if not u.is_authenticated:
            return False
        if request.method in SAFE_METHODS:
            return True
        return u.can_enter_field_records


class CanWriteOutreach(BasePermission):
    """
    Write access for Outreach Movement Register + Community Sessions.

    Mandatory for managers per the handoff; cannot delegate. Field staff are
    explicitly excluded — they record clinical encounters, not outreach.
    """
    def has_permission(self, request, view):
        u = request.user
        if not u.is_authenticated:
            return False
        if request.method in SAFE_METHODS:
            return True
        return u.can_enter_outreach_records


class CanWriteOrgRecord(BasePermission):
    """
    Fail-closed default write gate for org-scoped submission records that feed
    indicators. Read access is open to all authenticated users (org isolation
    is enforced by the queryset filter). Writes are denied to the view-only
    role (focal) and the survey-only role (ciprb_baseline) — neither should be
    able to create or alter records that drive the dashboards.

    Applied as OrgFilteredViewSet's default so a subclass that forgets an
    explicit permission_classes fails closed instead of inheriting the old bare
    IsAuthenticated (which let any logged-in role POST/PATCH/DELETE).
    """
    def has_permission(self, request, view):
        u = request.user
        if not u.is_authenticated:
            return False
        if request.method in SAFE_METHODS:
            return True
        return u.can_write_org_records


class CanAccessMPDSR(BasePermission):
    """
    MPDSR is CIPRB-owned. Dev + Supervisor see all; Org Lead only if
    organisation is CIPRB. Everyone else (managers, field staff, focal,
    baseline) gets 403.
    """
    def has_permission(self, request, view):
        u = request.user
        if not u.is_authenticated:
            return False
        if u.can_access_mpdsr:
            return True
        # Read-only visibility for monitoring orgs (CIPRB/UNFPA), e.g. a CIPRB
        # focal person viewing the MPDSR dashboard. Write stays restricted.
        return (
            request.method in SAFE_METHODS
            and u.organisation in MONITORING_ORGS
        )


class CanAccessFistulaCases(BasePermission):
    """
    Per-patient Fistula records (Corner + house-screening visits) carry
    decrypted survivor PII and are CIPRB-owned. Dev + Supervisor see all;
    Org Lead only if CIPRB. Managers (PHD/Bandhu), field staff, focal and
    baseline get 403. Audit FIX C1 — closes a cross-org PII leak where any
    authenticated manager/field-staff could read every fistula patient's
    decrypted name, husband name and phone.
    """
    def has_permission(self, request, view):
        u = request.user
        if not u.is_authenticated:
            return False
        if u.can_access_fistula_cases:
            return True
        # Read-only visibility for monitoring orgs (CIPRB/UNFPA). PHD/Bandhu
        # staff stay blocked from CIPRB survivor PII (audit FIX C1 preserved).
        return (
            request.method in SAFE_METHODS
            and u.organisation in MONITORING_ORGS
        )


class CanVerifyBaseline(BasePermission):
    """
    The D5 baseline study is CIPRB-conducted. Verifying (approving/rejecting)
    each interview and reading the response data is restricted to the CIPRB
    approver set: Dev + Supervisor (incl. UNFPA) + CIPRB Org Lead + CIPRB Manager
    (Tanjina — Rafi's 2026-06-26 directive: the CIPRB manager approves everything
    CIPRB, baseline included). Monitoring orgs (CIPRB/UNFPA) get read-only;
    PHD/Bandhu managers, field staff, focal and the survey-only role get 403 —
    they neither own nor verify this data (sensitive coded SRHR/violence answers).

    Stated EXPLICITLY rather than via `can_access_mpdsr` so this baseline gate
    cannot silently drift if the MPDSR PII proxy ever changes (the three CIPRB
    PII gates are deliberately independent).
    """
    def has_permission(self, request, view):
        u = request.user
        if not u.is_authenticated:
            return False
        if u.can_see_all_orgs:                       # Dev + Supervisor (UNFPA)
            return True
        if u.organisation == 'CIPRB' and u.role in ('org_lead', 'manager'):
            return True
        return (
            request.method in SAFE_METHODS
            and u.organisation in MONITORING_ORGS
        )


class CanViewBaseline(BasePermission):
    """READ visibility of the D5 baseline verification queue and verified
    responses. Monitoring orgs (CIPRB + UNFPA) plus the developer — i.e. exactly
    the people allowed to *see* the baseline tab. PHD/Bandhu managers, field
    staff, focal and the survey-only role get 403: the sensitive coded
    SRHR/violence answers never leave the CIPRB/UNFPA monitoring boundary.

    Approving is a separate, narrower gate (`CanApproveBaseline`) — UNFPA and the
    CIPRB org_lead (Sayeed) can see this queue but cannot act on it.
    """
    def has_permission(self, request, view):
        u = request.user
        return bool(
            u and u.is_authenticated
            and (u.organisation in MONITORING_ORGS or u.role == Role.DEVELOPER)
        )


class CanApproveBaseline(BasePermission):
    """WRITE (approve/reject) a D5 baseline interview. Deliberately tighter than
    `CanViewBaseline`: ONLY the developer and the CIPRB *manager* (Tanjina —
    Rafi's 2026-06-26 directive that verification of CIPRB baseline rests with
    Tanjina + developer). UNFPA supervisors and the CIPRB org_lead (Sayeed) are
    view-only here; PHD/Bandhu never reach baseline at all.

    Replaces the approve path of the old `CanVerifyBaseline`, which over-granted
    to every supervisor and to the CIPRB org_lead.
    """
    def has_permission(self, request, view):
        u = request.user
        return bool(
            u and u.is_authenticated
            and (
                u.role == Role.DEVELOPER
                or (u.organisation == Organisation.CIPRB and u.role == Role.MANAGER)
            )
        )


class CanApproveCIPRBAction(BasePermission):
    """MPDSR Action-Plan rows are district-level programme actions (NOT patient
    PII — that lives in MPDSRCase / the notifications). Approvable by the CIPRB
    approvers (Tanjina / Setu = role manager + organisation CIPRB) plus dev /
    UNFPA supervisors — i.e. anyone who can approve submissions and is CIPRB-
    scoped or sees all orgs. Deliberately NOT gated by CanAccessMPDSR, which
    requires org_lead+CIPRB and would lock the CIPRB manager approver out."""
    def has_permission(self, request, view):
        u = request.user
        return bool(
            u and u.is_authenticated and u.can_approve_submissions
            and (u.can_see_all_orgs or u.organisation == 'CIPRB')
        )


# ── Cross-org / multi-role membership classes ────────────────────────────────
#
# The legacy `IsSuperAdmin*` names have been removed entirely (audit FIX 1.2).
# The new names below carry the same membership rules but read accurately
# against the 7-role taxonomy — no role called "super admin" ever existed
# in the new taxonomy, and the rename eliminates a class of bugs where the
# reader assumed Sayeed (ORG_LEAD) had only narrow access.

class IsSupervisorOrOrgLead(BasePermission):
    """Cross-org read/write — accepts SUPERVISOR + ORG_LEAD.

    Replaces the deprecated `IsSuperAdmin`. CIPRB org lead (Sayeed) retains
    his full-CIPRB access plus read-only-others through this class."""
    def has_permission(self, request, view):
        u = request.user
        return u.is_authenticated and u.role in (Role.SUPERVISOR, Role.ORG_LEAD)


class IsSupervisorOrManager(BasePermission):
    """Generic authenticated-app-user gate — accepts everyone except FOCAL
    and CIPRB_BASELINE on the write path. Used by dashboard and tracker
    endpoints that every operational role consumes.

    Replaces the deprecated `IsSuperAdminOrManager`.

    FOCAL is the "view-only" role: it is allowed on read (SAFE_METHODS) so
    focal persons can see dashboards, but never on the write path."""
    def has_permission(self, request, view):
        u = request.user
        if not u.is_authenticated:
            return False
        if u.role in (
            Role.SUPERVISOR, Role.ORG_LEAD,
            Role.MANAGER, Role.DEVELOPER, Role.FIELD_STAFF,
        ):
            return True
        # View-only focal persons can read dashboards, not write.
        return u.role == Role.FOCAL and request.method in SAFE_METHODS


class IsSupervisorOrDeveloper(BasePermission):
    """Cross-org admin gate — accepts DEVELOPER + SUPERVISOR.

    Used where Rafi + Animesh + Rokhsana need access but not org leads."""
    def has_permission(self, request, view):
        u = request.user
        return u.is_authenticated and u.role in (Role.DEVELOPER, Role.SUPERVISOR)


class IsDeveloperOnly(BasePermission):
    """Developer-only gate — used by user-management endpoints (audit FIX 1.4).

    Supervisor retains all other access, but cannot manage users. Only
    Rafi (DEVELOPER) can create / modify / deactivate user accounts."""
    def has_permission(self, request, view):
        u = request.user
        return u.is_authenticated and u.role == Role.DEVELOPER


# ── OrgFilterMixin ────────────────────────────────────────────────────────────

class OrgFilterMixin:
    """
    DRF ViewSet mixin enforcing org-level queryset isolation.
    Supervisors, developers, and org leads see all rows (org leads see
    other-org rows read-only — write blocked at the permission layer).
    Managers / focal see only rows where `org_field` matches their org.

    Audit FIX 15.7 — field staff see only their OWN entries on top of the
    org filter. The mixin probes the model for an `approved_by` /
    `submitted_by` / `created_by` field (whichever exists, in that order)
    and adds a per-user filter when the user is FIELD_STAFF. Models without
    any such field fall back to plain org isolation (no leak — just a
    less-strict scope than the spec demands).
    """
    org_field = 'partner'

    # Candidate per-row owner fields, in priority order. The first one
    # that exists on the model is used.
    OWNER_FIELDS = ('submitted_by', 'created_by', 'approved_by', 'prescribed_by')

    def _owner_field_for(self, model):
        for fname in self.OWNER_FIELDS:
            if any(f.name == fname for f in model._meta.get_fields()):
                return fname
        return None

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if user.can_see_all_orgs or user.can_read_other_orgs:
            return qs
        # Monitoring orgs (CIPRB/UNFPA) read every org's rows. Writes are still
        # gated by the view's permission class (focal can't write).
        if user.organisation in (Organisation.CIPRB, Organisation.UNFPA):
            return qs

        # Org scope.
        qs = qs.filter(**{self.org_field: user.organisation})

        # Audit FIX 15.7 — field staff additionally restricted to own entries.
        from .models import Role
        if user.role == Role.FIELD_STAFF:
            owner = self._owner_field_for(qs.model)
            if owner is not None:
                qs = qs.filter(**{owner: user})

        return qs
