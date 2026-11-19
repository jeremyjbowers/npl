from django.db import migrations


def grant(apps, schema_editor):
    from npl.directors import grant_director_staff

    _, missing = grant_director_staff()
    if missing:
        print("No login account yet for: " + ", ".join(missing))


class Migration(migrations.Migration):

    dependencies = [
        ("npl", "0065_sim_player_team"),
    ]

    operations = [
        migrations.RunPython(grant, migrations.RunPython.noop),
    ]
