"""FERNET_KEY rotation: encrypted PII must survive a key change.

Before this, rotating FERNET_KEY made every existing ciphertext undecryptable
and all PII read back blank. These tests lock in the rotation path used after
the Railway env-var breach (Oct 2026).
"""
from cryptography.fernet import Fernet
from django.core.management import call_command
from django.test import TestCase, override_settings

from mpdsr.ciprb_models import SurgeryChecklist

OLD_KEY = Fernet.generate_key().decode()
NEW_KEY = Fernet.generate_key().decode()

SECRET_NAME = 'Fatema Begum'


def _make_row():
    return SurgeryChecklist.objects.create(
        organisation='CIPRB', district='Dhaka',
        operation_name='Caesarean section',
        patient_name=SECRET_NAME,
    )


class FernetRotationTest(TestCase):

    def test_fallback_key_keeps_old_data_readable(self):
        """Step 1 of a rotation: new primary + old key as fallback. Existing
        rows must still decrypt, so there is no blank-PII window on deploy."""
        with override_settings(FERNET_KEY=OLD_KEY, FERNET_KEY_FALLBACKS=[]):
            row = _make_row()

        with override_settings(FERNET_KEY=NEW_KEY, FERNET_KEY_FALLBACKS=[OLD_KEY]):
            self.assertEqual(
                SurgeryChecklist.objects.get(pk=row.pk).patient_name,
                SECRET_NAME)

    def test_without_fallback_old_data_is_unreadable(self):
        """The failure mode we are protecting against — proves the fallback is
        what saves the data, not luck."""
        with override_settings(FERNET_KEY=OLD_KEY, FERNET_KEY_FALLBACKS=[]):
            row = _make_row()

        with override_settings(FERNET_KEY=NEW_KEY, FERNET_KEY_FALLBACKS=[]):
            self.assertEqual(
                SurgeryChecklist.objects.get(pk=row.pk).patient_name, '')

    def test_rotate_command_re_encrypts_onto_new_key(self):
        """Step 2: after rotate_fernet_key --commit the data must read fine
        with the NEW key ALONE, so the old key can be retired."""
        with override_settings(FERNET_KEY=OLD_KEY, FERNET_KEY_FALLBACKS=[]):
            row = _make_row()

        with override_settings(FERNET_KEY=NEW_KEY, FERNET_KEY_FALLBACKS=[OLD_KEY]):
            call_command('rotate_fernet_key', '--commit', verbosity=0)

        # Fallback removed — this only works if the ciphertext was rewritten.
        with override_settings(FERNET_KEY=NEW_KEY, FERNET_KEY_FALLBACKS=[]):
            self.assertEqual(
                SurgeryChecklist.objects.get(pk=row.pk).patient_name,
                SECRET_NAME)

    def test_dry_run_changes_nothing(self):
        with override_settings(FERNET_KEY=OLD_KEY, FERNET_KEY_FALLBACKS=[]):
            row = _make_row()

        with override_settings(FERNET_KEY=NEW_KEY, FERNET_KEY_FALLBACKS=[OLD_KEY]):
            call_command('rotate_fernet_key', verbosity=0)   # no --commit

        with override_settings(FERNET_KEY=NEW_KEY, FERNET_KEY_FALLBACKS=[]):
            # Still only readable with the old key => nothing was rewritten.
            self.assertEqual(
                SurgeryChecklist.objects.get(pk=row.pk).patient_name, '')

    def test_rotation_is_idempotent(self):
        """Re-running must be a no-op, not a double-encrypt."""
        with override_settings(FERNET_KEY=OLD_KEY, FERNET_KEY_FALLBACKS=[]):
            row = _make_row()

        with override_settings(FERNET_KEY=NEW_KEY, FERNET_KEY_FALLBACKS=[OLD_KEY]):
            call_command('rotate_fernet_key', '--commit', verbosity=0)
            call_command('rotate_fernet_key', '--commit', verbosity=0)

        with override_settings(FERNET_KEY=NEW_KEY, FERNET_KEY_FALLBACKS=[]):
            self.assertEqual(
                SurgeryChecklist.objects.get(pk=row.pk).patient_name,
                SECRET_NAME)

    def test_gbv_and_client_pii_also_rotate(self):
        """Regression: GBVCase and Client use a DIFFERENT EncryptedCharField
        class (programs/models/gbv.py) than the fistula/mpdsr models. The first
        version of this rotation only matched the canonical class, so survivor
        and client PII would have been left on the retired key — and would have
        read back blank once the old key was dropped."""
        from programs.models import Client, GBVCase, ServiceCenter
        import datetime

        with override_settings(FERNET_KEY=OLD_KEY, FERNET_KEY_FALLBACKS=[]):
            centre = ServiceCenter.objects.create(
                organisation='PHD', name='Test centre', code='T001',
                district='Dhaka', is_active=True)
            gbv = GBVCase.objects.create(
                organisation='PHD', center=centre,
                interview_date=datetime.date(2026, 10, 1),
                incident_date=datetime.date(2026, 9, 30),
                survivor_name=SECRET_NAME,
                perpetrator_name='Someone Else')
            client = Client.objects.create(
                client_id='ROT-001', organisation='PHD', center=centre,
                name='Client', mother_name=SECRET_NAME)

        with override_settings(FERNET_KEY=NEW_KEY, FERNET_KEY_FALLBACKS=[OLD_KEY]):
            call_command('rotate_fernet_key', '--commit', verbosity=0)

        # New key ALONE must read them — proves both classes were rotated.
        with override_settings(FERNET_KEY=NEW_KEY, FERNET_KEY_FALLBACKS=[]):
            self.assertEqual(GBVCase.objects.get(pk=gbv.pk).survivor_name,
                             SECRET_NAME)
            self.assertEqual(GBVCase.objects.get(pk=gbv.pk).perpetrator_name,
                             'Someone Else')
            self.assertEqual(Client.objects.get(pk=client.pk).mother_name,
                             SECRET_NAME)

    def test_unknown_key_row_is_left_untouched(self):
        """A row encrypted with a key we no longer hold must be reported, not
        blanked or corrupted."""
        stray = Fernet.generate_key().decode()
        with override_settings(FERNET_KEY=stray, FERNET_KEY_FALLBACKS=[]):
            row = _make_row()

        with override_settings(FERNET_KEY=NEW_KEY, FERNET_KEY_FALLBACKS=[OLD_KEY]):
            call_command('rotate_fernet_key', '--commit', verbosity=0)

        # Untouched: still decryptable with its original key.
        with override_settings(FERNET_KEY=stray, FERNET_KEY_FALLBACKS=[]):
            self.assertEqual(
                SurgeryChecklist.objects.get(pk=row.pk).patient_name,
                SECRET_NAME)
