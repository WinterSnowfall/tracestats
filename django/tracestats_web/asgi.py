"""
ASGI config for tracestats_web project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/4.2/howto/deployment/asgi/
"""

import os
import sys

from django.core.asgi import get_asgi_application

sys.path.append('/opt/django')

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'tracestats_web.settings')

application = get_asgi_application()
