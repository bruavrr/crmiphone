from django import template
from urllib.parse import urlencode
register=template.Library()
@register.filter
def query(value): return urlencode(value)
@register.filter
def money(value):
    try: return f'R$ {float(value):,.2f}'.replace(',','X').replace('.',',').replace('X','.')
    except (TypeError,ValueError): return '—'
