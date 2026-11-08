"""The asset UIDs must follow the installation, not the first deployment.

These forms were originally deployed in one KoboToolbox account and the UIDs
were hardcoded in four places. Another organisation running this system
deploys the same XLSForms in their own account, where every UID is different.
With the UIDs hardcoded, that installation reads from, and writes into, forms
it does not own: the system_ref write-back fails, the lookup CSVs attach to
someone else's form, and the reconciliation loop calls every form missing.
"""
import os
from unittest import mock

from django.test import TestCase, override_settings

from indicators.models import KoboFormMapping
from programs.kobo_uids import DEFAULT_CIPRB_SLUG_TO_UID, uid_for

SLUG = 'ciprb_near_miss_v1'
DEFAULT_UID = DEFAULT_CIPRB_SLUG_TO_UID[SLUG]
OTHER_UID = 'aTheirOwnAccountUid123'


def set_registry_uid(slug, uid):
    """Set a registry row's UID.

    A data migration already seeds these rows, so the row normally exists;
    update it rather than creating a duplicate.
    """
    KoboFormMapping.objects.update_or_create(
        form_slug=slug,
        defaults={'form_label': slug, 'kobo_asset_uid': uid},
    )


class UidResolutionTests(TestCase):
    def test_falls_back_to_the_original_account(self):
        """An installation that configures nothing behaves as it always did."""
        set_registry_uid(SLUG, '')
        self.assertEqual(uid_for(SLUG), DEFAULT_UID)

    def test_the_registry_row_wins_over_the_default(self):
        """This is the route the setup guide uses, in step 9e."""
        set_registry_uid(SLUG, OTHER_UID)
        self.assertEqual(uid_for(SLUG), OTHER_UID)

    def test_a_blank_registry_row_does_not_blank_the_uid(self):
        set_registry_uid(SLUG, '')
        self.assertEqual(uid_for(SLUG), DEFAULT_UID)

    def test_the_environment_wins_over_everything(self):
        set_registry_uid(SLUG, OTHER_UID)
        with mock.patch.dict(
                os.environ, {'KOBO_ASSET_UID_CIPRB_NEAR_MISS_V1': 'aEnvWins0000000000000'}):
            self.assertEqual(uid_for(SLUG), 'aEnvWins0000000000000')

    def test_an_unknown_slug_returns_the_supplied_default(self):
        self.assertEqual(uid_for('not_a_form', 'fallback'), 'fallback')
        self.assertEqual(uid_for('', 'fallback'), 'fallback')


class ConsumersUseTheResolverTests(TestCase):
    """Every caller that talks out to KoboToolbox must go through it."""

    def setUp(self):
        set_registry_uid(SLUG, OTHER_UID)

    def test_replay_map_resolves_per_installation(self):
        from programs.ciprb_replay import ciprb_slug_to_uid
        self.assertEqual(ciprb_slug_to_uid()[SLUG], OTHER_UID)

    def test_fistula_exporter_targets_this_installation(self):
        from programs.management.commands.export_fistula_clients import (
            fistula_form_uids)
        set_registry_uid('ciprb_fistula_questions_v1', 'aFistulaOurs000000000')
        self.assertIn('aFistulaOurs000000000', [u for u, _ in fistula_form_uids()])

    def test_action_exporter_targets_this_installation(self):
        from programs.management.commands.export_mpdsr_actions import (
            action_form_uids)
        set_registry_uid('ciprb_mpdsr_response_plan_v1', 'aActionsOurs000000000')
        self.assertEqual([u for u, _ in action_form_uids()],
                         ['aActionsOurs000000000'])


class WebhookHealthCheckTests(TestCase):
    """The hook check matched a hardcoded hostname, so every other
    installation was told its webhooks pointed at the wrong place."""

    @override_settings(SIMPLE_PUBLIC_URL='https://simple.ciprb.org')
    def test_host_comes_from_the_configured_public_url(self):
        from mpdsr.reconcile import _our_host
        self.assertEqual(_our_host(), 'simple.ciprb.org')

    @override_settings(SIMPLE_PUBLIC_URL='')
    def test_blank_public_url_does_not_crash(self):
        from mpdsr.reconcile import _our_host
        self.assertEqual(_our_host(), '')
