from django.core.exceptions import ValidationError

def validate_file_size(value):
    max_size = 4194304 # 4 MB
    if value.size > max_size:
        raise ValidationError('File size exceeds the 4 MB limit.')

