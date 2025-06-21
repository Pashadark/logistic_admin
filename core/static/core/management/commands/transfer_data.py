# core/management/commands/transfer_data.py
from django.core.management.base import BaseCommand
from django.db import connection
from core.models import Shipment, Profile
from django.contrib.auth.models import User


class Command(BaseCommand):
    help = 'Transfer data from old SQLite to Django models'

    def handle(self, *args, **options):
        # Перенос пользователей
        with connection.cursor() as cursor:
            cursor.execute("SELECT * FROM users")
            old_users = cursor.fetchall()

            for user in old_users:
                user_id, username, first_name, last_name, *_ = user
                if not User.objects.filter(id=user_id).exists():
                    new_user = User.objects.create(
                        id=user_id,
                        username=username,
                        first_name=first_name,
                        last_name=last_name,
                        password='temp_password'  # Установите реальный пароль
                    )
                    Profile.objects.create(user=new_user)

        # Перенос отправок
        with connection.cursor() as cursor:
            cursor.execute("SELECT * FROM shipments")
            old_shipments = cursor.fetchall()

            for shipment in old_shipments:
                shipment_id, user_id, *rest = shipment
                if not Shipment.objects.filter(id=shipment_id).exists():
                    try:
                        user = User.objects.get(id=user_id)
                        Shipment.objects.create(
                            id=shipment_id,
                            user=user,
                            type=rest[0],
                            waybill_photo=rest[1],
                            product_photo=rest[2],
                            waybill_number=rest[3],
                            city=rest[4],
                            timestamp=rest[5],
                            comment=rest[6],
                            status=rest[7]
                        )
                    except User.DoesNotExist:
                        continue

        self.stdout.write(self.style.SUCCESS('Data transfer completed'))