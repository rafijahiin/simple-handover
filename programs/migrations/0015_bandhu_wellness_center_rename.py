"""
Rename the 8 Bandhu district centres from "Bandhu DIC X" to
"Bandhu Wellness Center X" (per Bandhu's correction: forms use "Wellness
Center", not "DIC"). Internal code (BND-DIC-0X) and center_type ('DIC') are
unchanged so indicator 1.8 ("drop-in centres established", the M&E-framework
wording) still counts these 8. The Dhaka KP Clinic is untouched.
"""
from django.db import migrations

RENAMES = {
    'BND-DIC-01': ('Bandhu Wellness Center Sunamganj',   'বন্ধু ওয়েলনেস সেন্টার সুনামগঞ্জ'),
    'BND-DIC-02': ('Bandhu Wellness Center Bandarban',   'বন্ধু ওয়েলনেস সেন্টার বান্দরবান'),
    'BND-DIC-03': ('Bandhu Wellness Center Chandpur',    'বন্ধু ওয়েলনেস সেন্টার চাঁদপুর'),
    'BND-DIC-04': ('Bandhu Wellness Center Noakhali',    'বন্ধু ওয়েলনেস সেন্টার নোয়াখালী'),
    'BND-DIC-05': ('Bandhu Wellness Center Chattogram',  'বন্ধু ওয়েলনেস সেন্টার চট্টগ্রাম'),
    'BND-DIC-06': ('Bandhu Wellness Center Narayanganj', 'বন্ধু ওয়েলনেস সেন্টার নারায়ণগঞ্জ'),
    'BND-DIC-07': ('Bandhu Wellness Center Habiganj',    'বন্ধু ওয়েলনেস সেন্টার হবিগঞ্জ'),
    'BND-DIC-08': ('Bandhu Wellness Center Manikganj',   'বন্ধু ওয়েলনেস সেন্টার মানিকগঞ্জ'),
}


def _forward(apps, schema_editor):
    ServiceCenter = apps.get_model('programs', 'ServiceCenter')
    for code, (name, name_bn) in RENAMES.items():
        ServiceCenter.objects.filter(code=code).update(name=name, name_bangla=name_bn)


def _reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('programs', '0014_adrrecord_manager_approved_at_and_more'),
    ]

    operations = [
        migrations.RunPython(_forward, _reverse),
    ]
