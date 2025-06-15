from django import forms
from .models import Shipment


class ShipmentFilterForm(forms.Form):
    STATUS_CHOICES = [('', 'Все статусы')] + Shipment.STATUS_CHOICES
    TYPE_CHOICES = [('', 'Все типы')] + Shipment.OPERATION_TYPES

    search = forms.CharField(
        required=False,
        label='Поиск',
        widget=forms.TextInput(attrs={'placeholder': 'Номер, город или комментарий'})
    )
    status = forms.ChoiceField(
        choices=STATUS_CHOICES,
        required=False,
        label='Статус'
    )
    type = forms.ChoiceField(
        choices=TYPE_CHOICES,
        required=False,
        label='Тип операции'
    )
    date_from = forms.DateField(
        required=False,
        label='С',
        widget=forms.DateInput(attrs={'type': 'date'})
    )
    date_to = forms.DateField(
        required=False,
        label='По',
        widget=forms.DateInput(attrs={'type': 'date'})
    )