"""
python manage.py seed_centers

Seeds ServiceCenter records for both organisations.

Gating
------
This command no-ops unless SEED_DB is truthy in the environment, so it
will not silently overwrite manager-edited centres on every Railway
container restart.

Idempotency
-----------
Uses get_or_create (NOT update_or_create) so existing rows are left
untouched. Only missing rows are added. Manager edits to lat/lng/name
survive.
"""
import os

from django.core.management.base import BaseCommand
from programs.models import ServiceCenter


def _seed_db_enabled() -> bool:
    raw = os.environ.get('SEED_DB', '').strip().lower()
    return raw not in ('', '0', 'false', 'no', 'off')

# Bandhu's 8 project districts each host a community-friendly Drop-In Centre
# (MIS Requirements doc, indicator 1.8 = 8 centres). The Dhaka Key Population
# Clinic (indicator 1.6 = 1) is a SEPARATE centre type so it never inflates
# the 8-DIC count.
BONDHU_DICS = [
    {'code': 'BND-DIC-01', 'name': 'Bandhu Wellness Center Sunamganj',
     'name_bangla': 'বন্ধু ওয়েলনেস সেন্টার সুনামগঞ্জ', 'center_type': 'DIC',
     'district': 'Sunamganj', 'upazila': 'Sunamganj Sadar', 'lat': 24.8817, 'lng': 91.4053},
    {'code': 'BND-DIC-02', 'name': 'Bandhu Wellness Center Bandarban',
     'name_bangla': 'বন্ধু ওয়েলনেস সেন্টার বান্দরবান', 'center_type': 'DIC',
     'district': 'Bandarban', 'upazila': 'Bandarban Sadar', 'lat': 22.1953, 'lng': 92.2184},
    {'code': 'BND-DIC-03', 'name': 'Bandhu Wellness Center Chandpur',
     'name_bangla': 'বন্ধু ওয়েলনেস সেন্টার চাঁদপুর', 'center_type': 'DIC',
     'district': 'Chandpur', 'upazila': 'Chandpur Sadar', 'lat': 23.2333, 'lng': 90.6500},
    {'code': 'BND-DIC-04', 'name': 'Bandhu Wellness Center Noakhali',
     'name_bangla': 'বন্ধু ওয়েলনেস সেন্টার নোয়াখালী', 'center_type': 'DIC',
     'district': 'Noakhali', 'upazila': 'Noakhali Sadar', 'lat': 22.8697, 'lng': 91.0994},
    {'code': 'BND-DIC-05', 'name': 'Bandhu Wellness Center Chattogram',
     'name_bangla': 'বন্ধু ওয়েলনেস সেন্টার চট্টগ্রাম', 'center_type': 'DIC',
     'district': 'Chittagong', 'upazila': 'Kotwali', 'lat': 22.3569, 'lng': 91.7832},
    {'code': 'BND-DIC-06', 'name': 'Bandhu Wellness Center Narayanganj',
     'name_bangla': 'বন্ধু ওয়েলনেস সেন্টার নারায়ণগঞ্জ', 'center_type': 'DIC',
     'district': 'Narayanganj', 'upazila': 'Narayanganj Sadar', 'lat': 23.6238, 'lng': 90.5000},
    {'code': 'BND-DIC-07', 'name': 'Bandhu Wellness Center Habiganj',
     'name_bangla': 'বন্ধু ওয়েলনেস সেন্টার হবিগঞ্জ', 'center_type': 'DIC',
     'district': 'Habiganj', 'upazila': 'Habiganj Sadar', 'lat': 24.3745, 'lng': 91.4155},
    {'code': 'BND-DIC-08', 'name': 'Bandhu Wellness Center Manikganj',
     'name_bangla': 'বন্ধু ওয়েলনেস সেন্টার মানিকগঞ্জ', 'center_type': 'DIC',
     'district': 'Manikganj', 'upazila': 'Manikganj Sadar', 'lat': 23.8617, 'lng': 90.0003},
    # Dhaka Key Population Clinic — distinct type (not a DIC).
    {'code': 'BND-KPC-01', 'name': 'Bandhu KP Clinic Dhaka',
     'name_bangla': 'বন্ধু কেপি ক্লিনিক ঢাকা', 'center_type': 'KP_CLINIC',
     'district': 'Dhaka', 'upazila': 'Dhaka Sadar', 'lat': 23.7104, 'lng': 90.4074},
]

# PHD's 9 brothel-based wellness centres — the real Master List from
# "Name and ID Number Of Wellness Center.docx" (PHD, May 2026).
# code = the official Wellness Centre ID (first-letter-of-district + SL).
# These 9 are the SL8 target. Beneficiary IDs use the SL-based prefix
# ({SL}-{4-digit}, e.g. Daulatdia = 1-0001).
PHD_BROTHELS = [
    {'sl': 1, 'code': 'R001', 'name': 'Daulatdia Wellness Center',
     'name_bangla': 'দৌলতদিয়া ওয়েলনেস সেন্টার',
     'center_type': 'BROTHEL', 'district': 'Rajbari', 'upazila': 'Goalanda',
     'lat': 23.7560, 'lng': 89.7800},
    {'sl': 2, 'code': 'J002', 'name': 'Maroawary Mandir Wellness Center',
     'name_bangla': 'মাড়োয়ারি মন্দির ওয়েলনেস সেন্টার',
     'center_type': 'BROTHEL', 'district': 'Jashore', 'upazila': 'Jashore Sadar',
     'lat': 23.1700, 'lng': 89.2100},
    {'sl': 3, 'code': 'B003', 'name': 'Kuchuyapotti Wellness Center',
     'name_bangla': 'কুচুয়াপট্টি ওয়েলনেস সেন্টার',
     'center_type': 'BROTHEL', 'district': 'Bagerhat', 'upazila': 'Bagerhat Sadar',
     'lat': 22.6500, 'lng': 89.7900},
    {'sl': 4, 'code': 'P004', 'name': 'Old Hospital Road Wellness Center',
     'name_bangla': 'ওল্ড হসপিটাল রোড ওয়েলনেস সেন্টার',
     'center_type': 'BROTHEL', 'district': 'Patuakhali', 'upazila': 'Patuakhali Sadar',
     'lat': 22.3600, 'lng': 90.3300},
    {'sl': 5, 'code': 'F005', 'name': 'Rathkhola Wellness Center',
     'name_bangla': 'রথখোলা ওয়েলনেস সেন্টার',
     'center_type': 'BROTHEL', 'district': 'Faridpur', 'upazila': 'Faridpur Sadar',
     'lat': 23.6000, 'lng': 89.8400},
    {'sl': 6, 'code': 'M006', 'name': 'Ganginerpar Wellness Center',
     'name_bangla': 'গাঙ্গিনারপাড় ওয়েলনেস সেন্টার',
     'center_type': 'BROTHEL', 'district': 'Mymensingh', 'upazila': 'Mymensingh Sadar',
     'lat': 24.7500, 'lng': 90.4000},
    {'sl': 7, 'code': 'J007', 'name': 'Raniganj Wellness Center',
     'name_bangla': 'রাণীগঞ্জ ওয়েলনেস সেন্টার',
     'center_type': 'BROTHEL', 'district': 'Jamalpur', 'upazila': 'Jamalpur Sadar',
     'lat': 24.9400, 'lng': 89.9400},
    {'sl': 8, 'code': 'T008', 'name': 'Kandapara Wellness Center',
     'name_bangla': 'কান্দাপাড়া ওয়েলনেস সেন্টার',
     'center_type': 'BROTHEL', 'district': 'Tangail', 'upazila': 'Tangail Sadar',
     'lat': 24.2500, 'lng': 89.9200},
    {'sl': 9, 'code': 'D009', 'name': 'Banishanta Wellness Center',
     'name_bangla': 'বানিশান্তা ওয়েলনেস সেন্টার',
     'center_type': 'BROTHEL', 'district': 'Khulna', 'upazila': 'Dacope',
     'lat': 22.5700, 'lng': 89.5000},
]

PHD_SUB_DICS = []  # PHD's real Master List has exactly the 9 wellness centres above.


class Command(BaseCommand):
    help = 'Seed ServiceCenter records for Bandhu (8 DICs + 1 Dhaka KP clinic) and PHD (9 wellness centres R001..D009)'

    def handle(self, *args, **options):
        if not _seed_db_enabled():
            self.stdout.write(
                'SEED_DB is not set — seed_centers is a no-op. '
                'Set SEED_DB=1 to enable.'
            )
            return

        created_count = 0
        skipped_count = 0

        all_centers = [
            ('Bandhu', c) for c in BONDHU_DICS
        ] + [
            ('PHD', c) for c in PHD_BROTHELS
        ] + [
            ('PHD', c) for c in PHD_SUB_DICS
        ]

        for org, data in all_centers:
            obj, created = ServiceCenter.objects.get_or_create(
                code=data['code'],
                defaults={
                    'organisation': org,
                    'name': data['name'],
                    'name_bangla': data.get('name_bangla', ''),
                    'center_type': data['center_type'],
                    'district': data.get('district', ''),
                    'upazila': data.get('upazila', ''),
                    'latitude': data.get('lat'),
                    'longitude': data.get('lng'),
                    'is_active': True,
                }
            )
            if created:
                created_count += 1
                self.stdout.write(self.style.SUCCESS(f'  Created: {obj}'))
            else:
                skipped_count += 1
                self.stdout.write(f'  Exists (untouched): {obj}')

        self.stdout.write(
            self.style.SUCCESS(
                f'\nseed_centers done. created={created_count} '
                f'exists_untouched={skipped_count}'
            )
        )
