# Generated by Django 4.1.7 on 2023-02-26 20:38

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("npl", "0021_collection_page_collection"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="collection",
            options={"ordering": ["name"]},
        ),
        migrations.AlterModelOptions(
            name="page",
            options={"ordering": ["-title"]},
        ),
    ]