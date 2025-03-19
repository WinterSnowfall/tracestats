from django import forms
from .validators import validate_file_size

class SearchForm(forms.Form):
    search_input = forms.CharField(max_length=68,
                                   min_length=2,
                                   widget=forms.TextInput(attrs={'class': 'search-input'}))

class FileUploadForm(forms.Form):
    authorization_token = forms.CharField(max_length=32,
                                          widget=forms.PasswordInput(attrs={'class': 'password-input'}))
    file_upload         = forms.FileField(validators=[validate_file_size],
                                          widget=forms.ClearableFileInput(attrs={'class': 'file-input'}))

