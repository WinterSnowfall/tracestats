from django import forms
from .validators import validate_file_size

API_FAMILY = [('All', 'All'), ('Direct3D', 'Direct3D'), ('Glide', 'Glide')]

class SearchForm(forms.Form):
    search_input = forms.CharField(max_length=74,
                                   min_length=2,
                                   widget=forms.TextInput(attrs={'class': 'search-input'}))

class FileUploadForm(forms.Form):
    authorization_token = forms.CharField(max_length=32,
                                          widget=forms.PasswordInput(attrs={'class': 'password-input'}))
    file_upload         = forms.FileField(validators=[validate_file_size],
                                          widget=forms.ClearableFileInput(attrs={'class': 'file-input'}))

class FilterSelectionForm(forms.Form):
    api_family_filter   = forms.CharField(widget=forms.RadioSelect(attrs={'class': 'radio-input'},
                                                                   choices=API_FAMILY))
