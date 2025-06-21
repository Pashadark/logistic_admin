from django import forms
from django.apps import apps


class ShipmentFilterForm(forms.Form):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        Shipment = apps.get_model('core', 'Shipment')

        STATUS_CHOICES = [('', 'Все статусы')] + Shipment.STATUS_CHOICES
        TYPE_CHOICES = [('', 'Все типы')] + Shipment.TYPE_CHOICES

        self.fields['status'].choices = STATUS_CHOICES
        self.fields['type'].choices = TYPE_CHOICES

    search = forms.CharField(
        required=False,
        label='Поиск',
        widget=forms.TextInput(attrs={'placeholder': 'Номер, город или комментарий'})
    )
    status = forms.ChoiceField(
        choices=[],  # Будет заполнено в __init__
        required=False,
        label='Статус'
    )
    type = forms.ChoiceField(
        choices=[],  # Будет заполнено в __init__
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