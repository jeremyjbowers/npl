# Generated by Django 4.1.7 on 2024-07-28 23:13

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("npl", "0033_player_fg_injury_description_player_fg_is_bench_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="player",
            name="npl_status",
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
    ]