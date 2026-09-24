import assert from 'node:assert/strict'
import test from 'node:test'
import { payoutCashForSubmit } from '../src/utils/payoutCash.js'

test('пустое поле — сумму считает сервер', () => {
  assert.equal(payoutCashForSubmit(''), null)
  assert.equal(payoutCashForSubmit('   '), null)
  assert.equal(payoutCashForSubmit(null), null)
})

test('число в поле уходит ровно тем, что видно', () => {
  assert.equal(payoutCashForSubmit('80000'), 80000)
  assert.equal(payoutCashForSubmit('12500.50'), 12500.5)
})
