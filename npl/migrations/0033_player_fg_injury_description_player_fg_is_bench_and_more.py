# Generated by Django 4.1.7 on 2024-07-28 16:20

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("npl", "0032_remove_auction_leading_bid_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="player",
            name="fg_injury_description",
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.AddField(
            model_name="player",
            name="fg_is_bench",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="player",
            name="fg_is_injured",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="player",
            name="fg_is_mlb40man",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="player",
            name="fg_is_starter",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="player",
            name="fg_role",
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.AddField(
            model_name="player",
            name="fg_role_type",
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
    ]