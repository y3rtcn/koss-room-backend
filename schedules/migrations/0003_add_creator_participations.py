from django.db import migrations


def add_creator_participations(apps, schema_editor):
    Schedule = apps.get_model("schedules", "Schedule")
    Participation = apps.get_model("schedules", "Participation")
    db_alias = schema_editor.connection.alias

    for schedule in Schedule.objects.using(db_alias).iterator():
        Participation.objects.using(db_alias).get_or_create(
            schedule_id=schedule.pk,
            user_id=schedule.creator_id,
        )


class Migration(migrations.Migration):
    dependencies = [
        ("schedules", "0002_participation"),
    ]

    operations = [
        migrations.RunPython(
            add_creator_participations,
            reverse_code=migrations.RunPython.noop,
        ),
    ]