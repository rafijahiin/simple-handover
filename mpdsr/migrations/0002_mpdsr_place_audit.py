from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('mpdsr', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='mpdsrcase',
            name='place_of_death',
            field=models.CharField(
                blank=True,
                choices=[('facility', 'Facility'), ('home', 'Home'), ('in_transit', 'In Transit')],
                default='facility',
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name='mpdsrcase',
            name='audit_trail',
            field=models.JSONField(blank=True, default=list),
        ),
    ]
