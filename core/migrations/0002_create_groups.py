from django.db import migrations
from django.contrib.auth.models import Group


def create_groups(apps, schema_editor):
    Group = apps.get_model('auth', 'Group')
    groups = ['Администратор', 'Разработчик', 'Офис-менеджер', 'Менеджер']
    for name in groups:
        Group.objects.get_or_create(name=name)


class Migration(migrations.Migration):
    dependencies = [
        ('core', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(create_groups),
    ]