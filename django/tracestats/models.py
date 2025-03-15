import secrets
import string
import math
from django.db import models
from django.utils.timezone import now

def generate_client_secret(length=32):
    characters = string.ascii_letters + string.digits + '_-'
    token = ''.join(secrets.choice(characters) for _ in range(length))
    return token

def round_up_two_decimals(value):
    return math.ceil(value * 100) / 100

class Tokens(models.Model):
    owner           = models.CharField(max_length=255, unique=True)
    token           = models.CharField(default=generate_client_secret, max_length=32, db_index=True)
    created_on      = models.DateTimeField(default=now)

class Trace(models.Model):
    name                = models.CharField(max_length=255, db_index=True)
    link                = models.CharField(max_length=255, null=True)
    binary_name         = models.CharField(max_length=255)
    updated_by          = models.ForeignKey(Tokens,
                                            on_delete=models.PROTECT)
    updated_last        = models.DateTimeField(default=now)
    api                 = models.CharField(max_length=10)
    api_calls_total     = models.IntegerField(null=True)
    render_states_total = models.IntegerField(null=True)
    query_types_total   = models.IntegerField(null=True)

    class Meta:
        # a certain appplication name can not occur more than once for a certain API
        constraints = [
            models.UniqueConstraint(fields=['name', 'api'], name='name_api')
        ]

class Stats(models.Model):
    trace      = models.ForeignKey(Trace,
                                   on_delete=models.CASCADE)
    created_on = models.DateTimeField(default=now)
    stat_type  = models.IntegerField()
    stat_name  = models.CharField(max_length=255, db_index=True)
    stat_count = models.IntegerField()

    class Meta:
        # a certain call can not occur more than once in a linked trace
        constraints = [
            models.UniqueConstraint(fields=['trace', 'stat_name'], name='trace_stat_name')
        ]

    @property
    def call_percentage(self):
        if self.stat_type == 1 and self.trace.api_calls_total is not None:
            # Don't display anything under 0.01 and round up to 2 demimal points of precision
            result = round_up_two_decimals(max((self.stat_count * 100) / self.trace.api_calls_total, 0.01))
            precision = 0 if result.is_integer() else (2 if (result * 100) % 10 != 0 else 1)
            return f'{result:.{precision}f}'
        return None

    @property
    def render_state_percentage(self):
        if self.stat_type == 5 and self.trace.render_states_total is not None:
            # Don't display anything under 0.01 and round up to 2 demimal points of precision
            result = round_up_two_decimals(max((self.stat_count * 100) / self.trace.render_states_total, 0.01))
            precision = 0 if result.is_integer() else (2 if (result * 100) % 10 != 0 else 1)
            return f'{result:.{precision}f}'
        return None

    @property
    def query_type_percentage(self):
        if self.stat_type == 6 and self.trace.query_types_total is not None:
            # Don't display anything under 0.01 and round up to 2 demimal points of precision
            result = round_up_two_decimals(max((self.stat_count * 100) / self.trace.query_types_total, 0.01))
            precision = 0 if result.is_integer() else (2 if (result * 100) % 10 != 0 else 1)
            return f'{result:.{precision}f}'
        return None

