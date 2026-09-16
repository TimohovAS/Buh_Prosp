import { useEffect, useRef, useState } from 'react'
import { reorderItems } from '../utils/reorderItems'

export default function useReorderableItems({ items, onChange, getKey, disabled = false, onBeforeMove }) {
  const [drag, setDrag] = useState(null)
  const pendingFocus = useRef(null)

  useEffect(() => {
    if (!disabled) return
    setDrag(null)
    pendingFocus.current = null
  }, [disabled])

  const move = (sourceKey, targetKey, after) => {
    if (disabled || sourceKey === targetKey) return
    onBeforeMove?.()
    onChange((current) => reorderItems(current, sourceKey, targetKey, after, getKey))
  }

  const getRowProps = (item, className = '') => {
    const key = getKey(item)
    const dragClass =
      drag?.sourceKey === key
        ? 'item-reorder-dragging'
        : drag?.targetKey === key
          ? `item-reorder-drop-${drag.after ? 'after' : 'before'}`
          : ''
    return {
      'data-reorderable-row': '',
      className: `reorderable-item ${className} ${dragClass}`.trim(),
      onDragOver: (event) => {
        if (disabled || !drag) return
        event.preventDefault()
        event.dataTransfer.dropEffect = 'move'
        const rect = event.currentTarget.getBoundingClientRect()
        const after = event.clientY > rect.top + rect.height / 2
        setDrag((current) =>
          current && (current.targetKey !== key || current.after !== after)
            ? { ...current, targetKey: key, after }
            : current
        )
      },
      onDrop: (event) => {
        if (disabled || !drag) return
        event.preventDefault()
        const rect = event.currentTarget.getBoundingClientRect()
        move(drag.sourceKey, key, event.clientY > rect.top + rect.height / 2)
        setDrag(null)
      },
    }
  }

  const getHandleProps = (item) => ({
    draggable: !disabled && items.length > 1,
    disabled: disabled || items.length < 2,
    onDragStart: (event) => {
      if (disabled || items.length < 2) {
        event.preventDefault()
        return
      }
      onBeforeMove?.()
      event.dataTransfer.effectAllowed = 'move'
      event.dataTransfer.setData('text/plain', String(getKey(item)))
      const row = event.currentTarget.closest('[data-reorderable-row]')
      const rect = row.getBoundingClientRect()
      event.dataTransfer.setDragImage(row, event.clientX - rect.left, event.clientY - rect.top)
      setDrag({ sourceKey: getKey(item), targetKey: getKey(item), after: false })
    },
    onDragEnd: () => setDrag(null),
    onKeyDown: (event) => {
      if (disabled || (event.key !== 'ArrowUp' && event.key !== 'ArrowDown')) return
      event.preventDefault()
      const index = items.findIndex((current) => getKey(current) === getKey(item))
      const after = event.key === 'ArrowDown'
      const target = items[index + (after ? 1 : -1)]
      if (!target) return
      move(getKey(item), getKey(target), after)
      const handle = event.currentTarget
      window.requestAnimationFrame(() => {
        if (!handle.isConnected) return
        handle.focus({ preventScroll: true })
        handle.scrollIntoView({ block: 'nearest', inline: 'nearest' })
      })
    },
  })

  const focusNewItem = (key) => {
    pendingFocus.current = key
  }

  const getInputRef = (item) => (input) => {
    if (!input || pendingFocus.current !== getKey(item)) return
    pendingFocus.current = null
    input.focus({ preventScroll: true })
    input.scrollIntoView({ block: 'nearest', inline: 'nearest' })
  }

  return { getRowProps, getHandleProps, focusNewItem, getInputRef }
}
