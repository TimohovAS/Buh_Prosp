import assert from 'node:assert/strict'
import test from 'node:test'
import { payoutCashForSubmit } from '../src/utils/payoutCash.js'

test('пустое поле — сумму считает сервер', () => {
  assert.equal(payoutCashForSubmit('', null), null)
  assert.equal(payoutCashForSubmit('   ', '80000'), null)
})

test('нетронутый подставленный остаток уходит как null, а не как явная сумма', () => {
  // Форма подставила сентябрьский остаток, потом поменяли дату, а ответ ещё не пришёл.
  assert.equal(payoutCashForSubmit('80000', '80000'), null)
})

test('число, введённое руками, уходит как есть', () => {
  assert.equal(payoutCashForSubmit('5000', '80000'), 5000)
  assert.equal(payoutCashForSubmit('80000', null), 80000)
  assert.equal(payoutCashForSubmit('12500.50', ''), 12500.5)
})
