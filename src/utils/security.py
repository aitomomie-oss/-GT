"""Protect text cells exported to spreadsheet applications."""
def csv_safe_text(value):
    if isinstance(value, str) and value.lstrip().startswith(('=', '+', '-', '@')):
        return "'" + value
    return value
