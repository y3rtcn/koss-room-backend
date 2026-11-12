from django.db import migrations


def create_room(apps, schema_editor):
    apps.get_model("attendance", "OccupancyState").objects.using(schema_editor.connection.alias).get_or_create(pk=1)


class Migration(migrations.Migration):
    dependencies = [("attendance", "0001_initial")]
    operations = [migrations.RunPython(create_room, migrations.RunPython.noop)]
