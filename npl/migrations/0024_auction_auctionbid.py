# Generated by Django 4.1.7 on 2023-03-11 02:11

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("npl", "0023_alter_collection_options_event"),
    ]

    operations = [
        migrations.CreateModel(
            name="Auction",
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
                ("closes", models.DateTimeField()),
                (
                    "player",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        to="npl.player",
                    ),
                ),
            ],
            options={
                "ordering": ["-closes"],
            },
        ),
        migrations.CreateModel(
            name="AuctionBid",
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
                ("max_bid", models.DecimalField(decimal_places=1, max_digits=4)),
                (
                    "auction",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE, to="npl.auction"
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
                "unique_together": {("team", "auction")},
            },
        ),
    ]