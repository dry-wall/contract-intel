from django import forms

from .models import Document


class DocumentUploadForm(forms.Form):
    file = forms.FileField()
    doc_type = forms.ChoiceField(choices=Document.DocType.choices, initial=Document.DocType.OTHER)
