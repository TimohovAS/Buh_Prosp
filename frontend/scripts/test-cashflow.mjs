import assert from 'node:assert/strict'
import { test } from 'node:test'
import {
  cashflowRange,
  cashflowDayCount,
  cashflowGrouping,
  shiftCashflowPeriod,
} from '../src/utils/cashflow.js'

test('calendar periods cover leap years and quarter/year boundaries', () => {
  assert.deepEqual(cashflowRange('month', '2024-02-29'), { from: '2024-02-01', to: '2024-02-29' })
  assert.deepEqual(cashflowRange('quarter', '2025-12-31'), { from: '2025-10-01', to: '2025-12-31' })
  assert.deepEqual(cashflowRange('year', '2025-08-10'), { from: '2025-01-01', to: '2025-12-31' })
  assert.deepEqual(cashflowRange('custom', '2025-08-10', '2024-12-15', '2025-01-06'), {
    from: '2024-12-15',
    to: '2025-01-06',
  })
})

test('previous/next periods do not skip February from a 31-day month', () => {
  assert.equal(shiftCashflowPeriod('2025-03-31', 'month', -1), '2025-02-01')
  assert.equal(shiftCashflowPeriod('2025-01-31', 'month', -1), '2024-12-01')
  assert.equal(shiftCashflowPeriod('2025-12-31', 'quarter', 1), '2026-03-01')
  assert.equal(shiftCashflowPeriod('2024-02-29', 'year', 1), '2025-02-01')
})

test('detail responds to duration and respects the daily limit', () => {
  assert.equal(cashflowDayCount('2026-03-01', '2026-03-31'), 31)
  assert.equal(cashflowGrouping('2026-09-01', '2026-09-07'), 'day')
  assert.equal(cashflowGrouping('2025-01-01', '2025-12-31'), 'month')
  assert.equal(cashflowGrouping('2020-01-01', '2025-12-31'), 'year')
  assert.equal(cashflowGrouping('2024-01-01', '2024-12-31', 'day'), 'day')
  assert.equal(cashflowGrouping('2024-01-01', '2025-01-01', 'day'), 'month')
  assert.equal(cashflowDayCount('', '2025-01-01'), 0)
  assert.equal(cashflowDayCount('2025-02-01', '2025-01-01'), 0)
})
