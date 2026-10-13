from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("npl", "0058_ifa_eligibility"),
    ]

    operations = [
        migrations.CreateModel(
            name="PlayerStatSeason",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("active", models.BooleanField(default=True)),
                ("created", models.DateTimeField(auto_now_add=True, null=True)),
                ("last_modified", models.DateTimeField(auto_now=True, null=True)),
                ("season", models.IntegerField()),
                ("is_career", models.BooleanField(default=False)),
                ("classification", models.CharField(blank=True, default="", max_length=255)),
                ("level", models.CharField(blank=True, default="", max_length=255)),
                ("hit_stats", models.JSONField(blank=True, null=True)),
                ("pitch_stats", models.JSONField(blank=True, null=True)),
                ("minors", models.BooleanField(default=False)),
                ("is_mlb", models.BooleanField(default=False)),
                ("is_starter", models.BooleanField(default=False)),
                ("is_bench", models.BooleanField(default=False)),
                ("is_injured", models.BooleanField(default=False)),
                ("injury_description", models.CharField(blank=True, default="", max_length=255)),
                ("role", models.CharField(blank=True, default="", max_length=255)),
                ("role_type", models.CharField(blank=True, default="", max_length=255)),
                ("roster_status", models.CharField(blank=True, default="", max_length=255)),
                ("mlb_org", models.CharField(blank=True, default="", max_length=255)),
                ("is_mlb40man", models.BooleanField(default=False)),
                ("player", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="stat_seasons", to="npl.player")),
            ],
            options={
                "ordering": ["-season", "classification"],
            },
        ),
        migrations.AddIndex(
            model_name="playerstatseason",
            index=models.Index(fields=["player", "season"], name="npl_players_player__6a0e1d_idx"),
        ),
        migrations.AddConstraint(
            model_name="playerstatseason",
            constraint=models.UniqueConstraint(fields=("player", "season", "classification", "is_career"), name="npl_stat_season_player_year_class"),
        ),
    ]
