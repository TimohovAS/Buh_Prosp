let nextEditorRowKey = 0

export const createEditorRowKey = () => `editor-row-${nextEditorRowKey++}`

export function reorderItems(items, sourceKey, targetKey, after, getKey) {
  if (sourceKey === targetKey) return items
  const sourceIndex = items.findIndex((item) => getKey(item) === sourceKey)
  const targetIndex = items.findIndex((item) => getKey(item) === targetKey)
  if (sourceIndex < 0 || targetIndex < 0) return items
  const insertionIndex = targetIndex + (after ? 1 : 0) - (sourceIndex < targetIndex ? 1 : 0)
  if (sourceIndex === insertionIndex) return items
  const next = [...items]
  const [item] = next.splice(sourceIndex, 1)
  next.splice(insertionIndex, 0, item)
  return next
}
