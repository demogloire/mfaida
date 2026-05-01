from django import template

register = template.Library()


@register.simple_tag
def stock_export_qs(request):
    """Suffixe '?a=1&b=2' pour conserver les filtres GET lors des téléchargements."""
    s = request.GET.urlencode()
    return f'?{s}' if s else ''
