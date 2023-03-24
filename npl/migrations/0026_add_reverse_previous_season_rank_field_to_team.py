from django.db import migrations, models
class Migration(migrations.Migration):
    dependencies = [
        ("npl", "0025_rename_auctionbid_nonmlbauctionbid_and_more"),
    ]

    operations = [
        migrations.AddField(model_name="team",
                            name="reverse_previous_season_rank",
                            field=models.IntegerField(blank=True, null=True))
    ]