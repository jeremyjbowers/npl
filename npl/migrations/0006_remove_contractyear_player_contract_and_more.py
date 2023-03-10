# Generated by Django 4.1.6 on 2023-02-10 11:09

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("npl", "0005_alter_player_options_contractyear"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="contractyear",
            name="player",
        ),
        migrations.CreateModel(
            name="Contract",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("active", models.BooleanField(default=True)),
                ("created", models.DateTimeField(auto_now_add=True, null=True)),
                ("last_modified", models.DateTimeField(auto_now=True, null=True)),
                ("total_amount", models.IntegerField(blank=True, null=True)),
                ("notes", models.TextField(blank=True, null=True)),
                ("can_buyout", models.BooleanField(default=False)),
                ("buyout", models.TextField(blank=True, null=True)),
                ("total_years", models.IntegerField(blank=True, null=True)),
                (
                    "player",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE, to="npl.player"
                    ),
                ),
                (
                    "team",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE, to="npl.team"
                    ),
                ),
            ],
            options={
                "abstract": False,
            },
        ),
        migrations.AddField(
            model_name="contractyear",
            name="contract",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                to="npl.contract",
            ),
        ),
    ]
