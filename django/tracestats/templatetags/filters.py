from django import template

register = template.Library()

#TODO: May need to consider other URL-type substitutions here
@register.filter(name='pcgwize')
def pcgwize(value):
    if not value:
        return ''

    return_string = value.replace('&', '%26')
    
    return return_string

