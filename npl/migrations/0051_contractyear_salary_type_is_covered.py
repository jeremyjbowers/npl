from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('npl', '0050_add_level_field'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='contractyear',
            options={'ordering': ['year']},
        ),
        migrations.AddField(
            model_name='contractyear',
            name='salary_type',
            field=models.CharField(choices=[('guaranteed', 'Guaranteed'), ('club_option', 'Club option'), ('vesting_option', 'Vesting option'), ('player_option', 'Player option / opt-out'), ('pre_arb_0', 'Pre-arbitration (0.000-0.171)'), ('pre_arb_1', 'Pre-arbitration (1.000-1.171)'), ('pre_arb_2', 'Pre-arbitration (2.000+)'), ('arbitration', 'Arbitration'), ('unknown', 'Unknown')], default='guaranteed', max_length=20),
        ),
        migrations.AddField(
            model_name='contractyear',
            name='is_covered',
            field=models.BooleanField(default=False),
        ),
    ]
