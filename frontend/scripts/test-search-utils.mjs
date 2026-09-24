import assert from 'node:assert/strict'
import test from 'node:test'
import { foldSearchText, matchesSearch } from '../src/utils/searchUtils.js'

// Те же случаи, что в backend/tests/test_client_search.py: правила обязаны совпадать
test('fold ignores script, diacritics and case', () => {
  assert.equal(foldSearchText('АИМА ДРУШТВО'), 'aima drustvo')
  assert.equal(foldSearchText('Vršac'), 'vrsac')
  assert.equal(foldSearchText('VRSAC'), 'vrsac')
  assert.equal(foldSearchText('Вршац'), 'vrsac')
  assert.equal(foldSearchText('Љубиша Њиве Џеп'), 'ljubisa njive dzep')
  assert.equal(foldSearchText('Ćevap Čačak Žabalj'), 'cevap cacak zabalj')
  assert.equal(foldSearchText(null), '')
})

test('fold treats đ, dj and d as the same letter', () => {
  for (const spelling of ['ĐURĐEVO', 'Djurdjevo', 'durdevo', 'Ђурђево']) {
    assert.equal(foldSearchText(spelling), 'durdevo')
  }
})

test('every query word must occur in some value', () => {
  assert.ok(matchesSearch('muzej vrsac', 'GRADSKI MUZEJ', 'Beogradski put, Vršac'))
  assert.ok(!matchesSearch('muzej novi sad', 'GRADSKI MUZEJ', 'Beogradski put, Vršac'))
  assert.ok(matchesSearch('   ', 'anything'))
})

test('project found by its Cyrillic client typed in Latin', () => {
  assert.ok(matchesSearch('aima', 'Servis klime', 'АИМА ДРУШТВО СА ОГРАНИЧЕНОМ ОДГОВОРНОШЋУ ВРШАЦ'))
  assert.equal(matchesSearch('aima', 'Servis klime', null), false)
})
