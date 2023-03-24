from django.db import migrations, models
class Migration(migrations.Migration):
    dependencies = [
        ("npl", "0026_add_reverse_previous_season_rank_field_to_team"),
    ]

    operations = [
        migrations.AddField(model_name="player",
                            name="is_on_outright_waivers",
                            field=models.BooleanField(default=False))
    ]