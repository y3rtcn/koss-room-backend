from django.db import migrations


def create_calendar(apps, schema_editor):
    apps.get_model("schedules", "CalendarLock").objects.using(schema_editor.connection.alias).get_or_create(pk=1)


class Migration(migrations.Migration):
    dependencies = [("schedules", "0001_initial")]
    operations = [migrations.RunPython(create_calendar, migrations.RunPython.noop)]
