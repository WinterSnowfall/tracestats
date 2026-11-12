from django.core.exceptions import ValidationError

MAX_FILE_SIZE = 16777216 # 16 MB

def validate_file_size(value):
    if value.size > MAX_FILE_SIZE:
        raise ValidationError('File size exceeds the 16 MB limit.')
