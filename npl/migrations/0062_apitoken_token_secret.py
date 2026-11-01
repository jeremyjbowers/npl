from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("npl", "0061_trade_public_id"),
    ]

    operations = [
        migrations.AddField(
            model_name="apitoken",
            name="token_secret",
            field=models.CharField(blank=True, default="", max_length=128),
        ),
    ]
