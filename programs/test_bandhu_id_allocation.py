"""Spondon issues the Bandhu beneficiary id; the field worker never types one.

Until 2026-08-06 the 4-digit serial was hand-typed and guarded only by a
constraint against bandhu_clients.csv. That CSV is a snapshot which reaches a
phone only when the device re-downloads the form, so two peer educators
registering different people in the same sitting could not see each other's
brand-new number and neither was blocked: 68 ids ended up shared by 165 people,
and because handle_bandhu_mother_list keeps the first arrival and drops the
rest, 84 of those people were never created in Spondon at all.

These tests pin the replacement: allocation happens once, on the server.
"""
from unittest import mock

from django.core.cache import cache
from django.test import TestCase

from programs.bandhu_handlers import handle_bandhu_mother_list
from programs.models import Client, ServiceCenter


def _payload(kobo_id, name, dist='02', existing=None, **extra):
    p = {
        'center_code': 'BAN-002',
        'centre_district_code': dist,
        'ml_name': name,
        'ml_gender': '05',
        '_id': str(kobo_id),
        '_submitted_by': 'bandhu_worker',
    }
    if existing:
        p['ml_id_no'] = existing
    p.update(extra)
    return p


class BandhuIdAllocationTest(TestCase):
    def setUp(self):
        cache.clear()
        self.center = ServiceCenter.objects.create(
            organisation='Bandhu', name='Bandhu centre', code='BAN-002',
            center_type=ServiceCenter.DIC, district='Chattogram', is_active=True,
        )
        # the write-back is a live Kobo call; never touch the network in tests
        patcher = mock.patch('programs.bandhu_handlers._writeback_kobo_id')
        self.writeback = patcher.start()
        self.addCleanup(patcher.stop)

    def _reg(self, kobo_id, name, **kw):
        return handle_bandhu_mother_list(_payload(kobo_id, name, **kw),
                                         lat=23.7, lng=90.4)

    # ── allocation ────────────────────────────────────────────────────────
    def test_first_registration_at_a_centre_gets_0001(self):
        resp = self._reg(9001, 'Asha')
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(Client.objects.get(kobo_submission_id='9001').client_id,
                         '02-0001')

    def test_ids_are_sequential_and_never_repeat(self):
        for i, nm in enumerate(['Asha', 'Bina', 'Chaya'], start=1):
            self._reg(9000 + i, nm)
        got = sorted(Client.objects.values_list('client_id', flat=True))
        self.assertEqual(got, ['02-0001', '02-0002', '02-0003'])

    def test_two_centres_count_independently(self):
        self._reg(9001, 'Asha', dist='02')
        self._reg(9002, 'Bina', dist='03')
        self.assertEqual(Client.objects.get(kobo_submission_id='9001').client_id,
                         '02-0001')
        self.assertEqual(Client.objects.get(kobo_submission_id='9002').client_id,
                         '03-0001')

    def test_the_worker_cannot_cause_a_collision_any_more(self):
        """The whole point: two registrations that would once have both been
        typed as 0001 now land on different ids and BOTH survive."""
        self._reg(9101, 'Asha')
        self._reg(9102, 'Bina')
        self.assertEqual(Client.objects.count(), 2)
        self.assertEqual(len(set(Client.objects.values_list('client_id', flat=True))), 2)

    # ── idempotency ───────────────────────────────────────────────────────
    def test_redelivery_does_not_burn_a_second_id(self):
        self._reg(9001, 'Asha')
        resp = self._reg(9001, 'Asha')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(Client.objects.count(), 1)

    # ── existing ids still work ───────────────────────────────────────────
    def test_typed_existing_id_is_honoured_and_nothing_is_allocated(self):
        resp = self._reg(9001, 'Asha', existing='02-0777')
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(Client.objects.get(kobo_submission_id='9001').client_id,
                         '02-0777')

    def test_existing_id_of_another_person_does_not_overwrite_her(self):
        """Asha keeps her id, and Bina is registered rather than discarded.

        Until 2026-08-26 this returned 200 and Bina was never registered at
        all, with nothing on screen to say so. Manual entry makes that far more
        likely, so the collision now reallocates instead of dropping her.
        """
        self._reg(9001, 'Asha', existing='02-0777')
        resp = self._reg(9002, 'Bina', existing='02-0777')
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(Client.objects.get(client_id='02-0777').name, 'Asha')
        bina = Client.objects.get(name='Bina')
        self.assertNotEqual(bina.client_id, '02-0777')
        self.assertTrue(bina.client_id.startswith('02-'))

    # ── the typo guard ────────────────────────────────────────────────────
    def test_a_birth_year_typed_as_a_serial_does_not_drag_new_ids_into_the_1900s(self):
        """03-1980 and 05-1988 are real: someone typed a birth year into the old
        serial box. Taking max()+1 blindly would issue 03-1981 to the next
        woman who registers."""
        self._reg(9001, 'Asha', dist='03')
        Client.objects.create(organisation='Bandhu', client_id='03-1980',
                              name='typo row', center=self.center)
        self._reg(9002, 'Bina', dist='03')
        self.assertEqual(Client.objects.get(kobo_submission_id='9002').client_id,
                         '03-0002')

    # ── guard rails ───────────────────────────────────────────────────────
    def test_missing_centre_code_is_rejected_rather_than_guessed(self):
        p = _payload(9001, 'Asha')
        p['centre_district_code'] = ''
        resp = handle_bandhu_mother_list(p, lat=23.7, lng=90.4)
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(Client.objects.count(), 0)

    def test_the_issued_id_is_written_back_to_kobo(self):
        self._reg(9001, 'Asha')
        self.assertTrue(self.writeback.called)
        args = self.writeback.call_args[0]
        self.assertEqual(args[1], '9001')
        self.assertEqual(args[2], '02-0001')
