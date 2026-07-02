from collections import defaultdict
from decimal import Decimal
from compare_cash_bank_exports import cash_rows, bank_cash_rows, money

by_type = defaultdict(lambda: {'count':0, 'in':Decimal('0'), 'out':Decimal('0')})
for r in cash_rows:
    item = by_type[r.get('Тип','')]
    item['count'] += 1
    item['in'] += money(r.get('Приток'))
    item['out'] += money(r.get('Отток'))
print('CASH TYPES')
for typ, v in sorted(by_type.items()):
    print(f"{typ}|count={v['count']}|in={v['in']}|out={v['out']}|net={v['in']-v['out']}")
print('\nTOP 10 CASH')
for r in cash_rows[:10]:
    print('|'.join([r.get('Дата',''), r.get('Тип',''), r.get('Описание',''), r.get('Источник',''), r.get('Приток',''), r.get('Отток',''), r.get('Остаток после операции','')]))
print('\nBANK CASH SUM')
amount = sum((money(r.get('Сумма (RSD)')) for r in bank_cash_rows), Decimal('0'))
print(amount)
