import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'logistic_admin.settings')
django.setup()

from core.models import Shipment

def check_data():
    print(f"Всего записей: {Shipment.objects.count()}")
    for shipment in Shipment.objects.all()[:5]:
        print(f"ID: {shipment.id}, Накладная: {shipment.waybill_number}, Город: {shipment.city}")

if __name__ == '__main__':
    check_data()