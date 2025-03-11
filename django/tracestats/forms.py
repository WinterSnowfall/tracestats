from django import forms

class SearchForm(forms.Form):
    search_input = forms.CharField(max_length=68,
                                   min_length=2,
                                   widget=forms.TextInput(attrs={'class': 'search-input'}))

class FileUploadForm(forms.Form):
    authorization_token = forms.CharField(max_length=32,
                                          widget=forms.PasswordInput(attrs={'class': 'password-input'}))
    file_upload         = forms.FileField()

