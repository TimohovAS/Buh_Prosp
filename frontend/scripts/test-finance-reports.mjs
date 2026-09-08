import assert from 'node:assert/strict'
import { test } from 'node:test'
import { selectReceivables, receivablesTotal } from '../src/utils/receivables.js'

const invoices = [
  {
    income_id: 1,
    invoice_number: 'INV-10',
    client_name: 'Alpha',
    amount: '100.01',
    days_overdue: 31,
    aging_bucket: '31_60',
    due_date: '2025-01-01',
  },
  {
    income_id: 2,
    invoice_number: 'INV-2',
    client_name: 'Beta',
    amount: '20.02',
    days_overdue: 0,
    aging_bucket: 'not_due',
    due_date: '2025-03-01',
  },
  {
    income_id: 3,
    invoice_number: 'INV-3',
    client_name: 'Alpha',
    amount: '9.03',
    days_overdue: null,
    aging_bucket: 'no_due',
    due_date: null,
  },
]

test('overdue and aging filters distinguish missing due dates and retain search', () => {
  assert.deepEqual(
    selectReceivables(invoices, 'overdue', '', 'days_overdue', false).map((x) => x.income_id),
    [1]
  )
  assert.deepEqual(
    selectReceivables(invoices, 'no_due', 'ALPHA', 'amount', false).map((x) => x.income_id),
    [3]
  )
  assert.equal(selectReceivables(invoices, 'overdue', 'Beta', 'amount', false).length, 0)
})

test('sort uses numbers for serialized decimal amounts, natural invoice order, and missing dates last', () => {
  assert.deepEqual(
    selectReceivables(invoices, 'all', '', 'amount', true).map((x) => x.income_id),
    [3, 2, 1]
  )
  assert.deepEqual(
    selectReceivables(invoices, 'all', '', 'invoice_number', true).map((x) => x.income_id),
    [2, 3, 1]
  )
  assert.deepEqual(
    selectReceivables(invoices, 'all', '', 'due_date', false).map((x) => x.income_id),
    [2, 1, 3]
  )
  assert.deepEqual(
    selectReceivables(invoices, 'all', '', 'due_date', true).map((x) => x.income_id),
    [1, 2, 3]
  )
  assert.deepEqual(
    invoices.map((x) => x.income_id),
    [1, 2, 3]
  )
})

test('filtered totals add cents exactly and reflect only the visible subset', () => {
  assert.equal(receivablesTotal(invoices), 129.06)
  assert.equal(receivablesTotal(selectReceivables(invoices, 'all', 'Alpha', 'amount', false)), 109.04)
  assert.equal(receivablesTotal([{ amount: 0.1 }, { amount: 0.2 }]), 0.3)
})
