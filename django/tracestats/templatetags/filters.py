from django import template

register = template.Library()

#TODO: May need to consider other URL-type substitutions here
@register.filter(name='urlize')
def basic_urlize(value):
    if not value:
        return ''

    return value.replace('&', '%26')

@register.filter(name='unmark_urlize')
def unmark_urlize(value):
    if not value:
        return ''

    return basic_urlize(value.replace('<mark>', '').replace('</mark>', ''))

@register.filter(name='decode_api')
def decode_api(dictionary, key):
    return dictionary.get(key, "Unknown")
