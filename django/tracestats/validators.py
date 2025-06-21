from django.core.exceptions import ValidationError

def validate_file_size(value):
    max_size = 16777216 # 16 MB
    if value.size > max_size:
        raise ValidationError('File size exceeds the 16 MB limit.')

