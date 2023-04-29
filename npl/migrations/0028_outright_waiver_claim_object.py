
from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):
    dependencies = [
        ("npl", "0027_add_outright_waiver_to_players"),
    ]

    operations = [
        migrations.CreateModel(
            name='OutrightWaiverClaim',
            fields=[
                ("active", models.BooleanField(default=True)),
                ("created", models.DateTimeField(auto_now_add=True, null=True)),
                ("last_modified", models.DateTimeField(auto_now=True, null=True)),
                ("player", models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.CASCADE,
                    to="npl.player"
                )),
                ("team", models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.CASCADE,
                    to="npl.team"
                )),
                ("submission_time",  models.DateTimeField()),
                ("deadline", models.DateTimeField())
            ]
        )
    ]