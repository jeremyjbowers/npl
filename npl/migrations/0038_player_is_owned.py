# Generated by Django 4.1.7 on 2025-01-26 22:29

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("npl", "0037_remove_player_fg_injury_description_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="player",
            name="is_owned",
            field=models.BooleanField(default=False),
        ),
    ]
