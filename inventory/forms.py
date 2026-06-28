from django import forms
from .models import Articulo, Almacen

class ArticuloAdminForm(forms.ModelForm):
    almacen_ingreso_seriales = forms.ModelChoiceField(
        queryset=Almacen.objects.all(),
        required=False,
        label='Almacén de Destino',
        help_text='Seleccione el almacén donde ingresarán los nuevos seriales masivos.',
    )
    carga_masiva_seriales = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 4, 'placeholder': 'Pegue aquí los seriales separados por coma o salto de línea...'}),
        required=False,
        label='Carga Masiva de Seriales',
        help_text='Opcional. Ingrese múltiples seriales para inyectarlos en bloque tras guardar el artículo.',
    )

    class Meta:
        model = Articulo
        fields = '__all__'
