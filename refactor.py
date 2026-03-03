import sys
import re

file_path = r'd:\Work\Programming\Buh_Prosp\backend\routers\income_router.py'
with open(file_path, 'r', encoding='utf-8') as f:
    text = f.read()

# We will remove the large chunk between EF_NS = ... and @router.get("",
match_start = re.search(r'EF_NS = \{', text)
match_end = re.search(r'@router\.get\(\"\",[^\n]*\nasync def list_income\(', text)

if match_start and match_end:
    before = text[:match_start.start()]
    after = text[match_end.start():]
    
    # We also need to remove _invoice_year_from_number
    after = re.sub(r'def _invoice_year_from_number.*?\n\n\n', '\n', after, flags=re.DOTALL)
    after = re.sub(r'def _invoice_year_from_number.*?\n\n', '\n', after, flags=re.DOTALL)

    import_statement = '''from backend.income_service import (
    to_number_year_format,
    has_invoice_duplicate,
    parse_efaktura_invoice,
    invoice_year_from_number,
    normalize_pib,
    normalize_name,
)

'''
    new_text = before + import_statement + after
    
    # Also replace usages:
    new_text = new_text.replace('_to_number_year_format', 'to_number_year_format')
    new_text = new_text.replace('_has_invoice_duplicate', 'has_invoice_duplicate')
    new_text = new_text.replace('_parse_efaktura_invoice', 'parse_efaktura_invoice')
    new_text = new_text.replace('_invoice_year_from_number', 'invoice_year_from_number')
    new_text = new_text.replace('_normalize_pib', 'normalize_pib')
    new_text = new_text.replace('_normalize_name', 'normalize_name')

    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(new_text)
    print('Refactoring successful!')
else:
    print('Failed to find start/end marks, verify regex')
