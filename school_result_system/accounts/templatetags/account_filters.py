from django import template

register = template.Library()

@register.filter
def get_item(dictionary, key):
    """Return value from dictionary for given key"""
    return dictionary.get(key, '')


@register.filter
def dict_get(dictionary, key):
    return dictionary.get(key, '')
