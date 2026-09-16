import assert from 'node:assert/strict'
import test from 'node:test'
import { createEditorRowKey, reorderItems } from '../src/utils/reorderItems.js'

const getKey = (item) => item.key
const makeItems = () =>
  ['a', 'b', 'c', 'd'].map((key, index) =>
    Object.freeze({ key, name: key.toUpperCase(), quantity: index + 1, price: 100, note: `Note ${key}` })
  )

for (const [source, target, after, expected] of [
  ['d', 'b', false, 'adbc'],
  ['a', 'd', true, 'bcda'],
  ['d', 'a', false, 'dabc'],
  ['a', 'c', false, 'bacd'],
  ['c', 'a', true, 'acbd'],
  ['b', 'c', true, 'acbd'],
  ['c', 'b', false, 'acbd'],
]) {
  test(`move ${source} ${after ? 'after' : 'before'} ${target}`, () => {
    const items = Object.freeze(makeItems())
    const moved = reorderItems(items, source, target, after, getKey)
    assert.equal(moved.map(getKey).join(''), expected)
    assert.equal(items.map(getKey).join(''), 'abcd')
    for (const item of items)
      assert.strictEqual(
        moved.find((row) => row.key === item.key),
        item
      )
  })
}

test('self drops, adjacent unchanged drops and missing rows leave the list untouched', () => {
  const items = Object.freeze(makeItems())
  for (const [source, target, after] of [
    ['a', 'a', true],
    ['b', 'c', false],
    ['c', 'b', true],
    ['missing', 'a', true],
    ['a', 'missing', false],
  ]) {
    assert.strictEqual(reorderItems(items, source, target, after, getKey), items)
  }
  const empty = []
  assert.strictEqual(reorderItems(empty, 'a', 'b', false, getKey), empty)
})

test('source document links follow their positions, even with identical descriptions', () => {
  const rows = [
    { entry_id: 12, name: 'Service', amount: 200, available: 250 },
    { entry_id: 23, name: 'Service', amount: 350, available: 400 },
  ]
  const moved = reorderItems(rows, 23, 12, false, (row) => row.entry_id)
  assert.deepEqual(moved, [rows[1], rows[0]])
  assert.equal(
    moved.reduce((sum, row) => sum + row.amount, 0),
    550
  )
})

test('new unsaved rows have distinct keys and can be reordered after deletion', () => {
  const rows = Array.from({ length: 3 }, () => ({ key: createEditorRowKey(), name: '' }))
  assert.equal(new Set(rows.map(getKey)).size, 3)
  const remaining = [rows[0], rows[2]]
  assert.deepEqual(reorderItems(remaining, rows[2].key, rows[0].key, false, getKey), [rows[2], rows[0]])
})
