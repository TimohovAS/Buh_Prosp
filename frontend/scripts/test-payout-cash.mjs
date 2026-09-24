import assert from 'node:assert/strict'
import test from 'node:test'
import { payoutCashForSubmit, payoutPreviewState } from '../src/utils/payoutCash.js'

test('пустое поле — сумму считает сервер', () => {
  assert.equal(payoutCashForSubmit(''), null)
  assert.equal(payoutCashForSubmit('   '), null)
  assert.equal(payoutCashForSubmit(null), null)
})

test('число в поле уходит ровно тем, что видно', () => {
  assert.equal(payoutCashForSubmit('80000'), 80000)
  assert.equal(payoutCashForSubmit('12500.50'), 12500.5)
})

test('сохранять можно только с серверным расчётом текущего черновика', () => {
  const data = { cash_paid_amount: '80000.00' }
  assert.deepEqual(payoutPreviewState({ key: 'b', data }, 'b'), { ready: true, failed: false, data })
  // Ответ пришёл для прежнего черновика — ждём новый.
  assert.deepEqual(payoutPreviewState({ key: 'a', data }, 'b'), { ready: false, failed: false, data: null })
  assert.deepEqual(payoutPreviewState(null, 'b'), { ready: false, failed: false, data: null })
})

test('ошибка расчёта не открывает сохранение', () => {
  assert.deepEqual(payoutPreviewState({ key: 'b', data: null, failed: true }, 'b'), {
    ready: false,
    failed: true,
    data: null,
  })
})
