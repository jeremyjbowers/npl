# Generated by Django 4.1.6 on 2023-02-26 12:33

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("npl", "0014_transactiontype_transaction_acquiring_team_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="transaction",
            name="raw_acquiring_team",
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.AddField(
            model_name="transaction",
            name="raw_player",
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.AddField(
            model_name="transaction",
            name="raw_team",
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
    ]