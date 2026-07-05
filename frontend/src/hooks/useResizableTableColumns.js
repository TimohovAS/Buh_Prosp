import { useEffect } from 'react'
import { useLocation } from 'react-router-dom'

const STORAGE_KEY = 'resizableTableColumns:v1'
const RESIZE_EDGE_PX = 6
const RESIZE_START_THRESHOLD_PX = 4
const MIN_COLUMN_WIDTH = 64

function loadStoredWidths() {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}')
  } catch {
    return {}
  }
}

function saveStoredWidths(next) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(next))
}

function getResizableTables() {
  return Array.from(document.querySelectorAll('.table-wrap table')).filter((table) => {
    const slot = table.closest('.route-cache-slot')
    if (slot && !slot.classList.contains('active')) return false
    if (table.querySelector('colgroup:not([data-resizable-columns="true"])')) return false
    return true
  })
}

function getTableKey(table) {
  const tables = getResizableTables()
  const index = Math.max(tables.indexOf(table), 0)
  return `${window.location.pathname}::${index}::${table.className || 'table'}`
}

function getHeaderCells(table) {
  return Array.from(table.querySelectorAll('thead tr:first-child th'))
}

function getColumnCount(table) {
  const firstRow = table.querySelector('thead tr:first-child') || table.querySelector('tr')
  return firstRow ? firstRow.children.length : 0
}

function getOrCreateColgroup(table) {
  let colgroup = table.querySelector('colgroup[data-resizable-columns="true"]')
  if (!colgroup) {
    colgroup = document.createElement('colgroup')
    colgroup.dataset.resizableColumns = 'true'
    table.insertBefore(colgroup, table.firstChild)
  }

  const columnCount = getColumnCount(table)
  while (colgroup.children.length < columnCount) {
    colgroup.appendChild(document.createElement('col'))
  }
  while (colgroup.children.length > columnCount) {
    colgroup.removeChild(colgroup.lastChild)
  }
  return colgroup
}

function getCurrentWidths(table) {
  const headers = getHeaderCells(table)
  return headers.map((header) => Math.max(MIN_COLUMN_WIDTH, Math.round(header.getBoundingClientRect().width)))
}

function applyWidths(table, widths) {
  if (!widths?.length) return
  const colgroup = getOrCreateColgroup(table)
  widths.forEach((width, index) => {
    if (!colgroup.children[index]) return
    colgroup.children[index].style.width = `${Math.max(MIN_COLUMN_WIDTH, Math.round(width))}px`
  })
  const totalWidth = widths.reduce((sum, width) => sum + Math.max(MIN_COLUMN_WIDTH, Math.round(width)), 0)
  table.style.tableLayout = 'fixed'
  table.style.width = `${totalWidth}px`
  table.style.minWidth = `${totalWidth}px`
}

function persistWidths(table, widths) {
  const stored = loadStoredWidths()
  stored[getTableKey(table)] = widths.map((width) => Math.max(MIN_COLUMN_WIDTH, Math.round(width)))
  saveStoredWidths(stored)
}

function resetTableWidths(table) {
  const stored = loadStoredWidths()
  delete stored[getTableKey(table)]
  saveStoredWidths(stored)
  table.removeAttribute('style')
  const colgroup = table.querySelector('colgroup[data-resizable-columns="true"]')
  if (colgroup) colgroup.remove()
}

function restoreTables() {
  const stored = loadStoredWidths()
  getResizableTables().forEach((table) => {
    const widths = stored[getTableKey(table)]
    if (Array.isArray(widths)) applyWidths(table, widths)
  })
}

function findResizableHeader(event) {
  for (const table of getResizableTables()) {
    const tableRect = table.getBoundingClientRect()
    if (event.clientY < tableRect.top || event.clientY > tableRect.bottom) continue

    const headers = getHeaderCells(table)
    for (let index = 0; index < headers.length - 1; index += 1) {
      const header = headers[index]
      const rect = header.getBoundingClientRect()
      const isInHeaderY = event.clientY >= rect.top && event.clientY <= rect.bottom
      const isNearRightEdge = Math.abs(event.clientX - rect.right) <= RESIZE_EDGE_PX

      if (isInHeaderY && isNearRightEdge) return { table, header, index }
    }
  }

  return null
}

export default function useResizableTableColumns() {
  const location = useLocation()

  useEffect(() => {
    restoreTables()
    const observer = new MutationObserver(() => restoreTables())
    observer.observe(document.body, { childList: true, subtree: true })
    return () => observer.disconnect()
  }, [location.pathname])

  useEffect(() => {
    let activeResize = null
    let pendingResize = null
    let suppressNextClick = false
    const previousCursor = { value: '' }
    const previousUserSelect = { value: '' }

    const stopResize = () => {
      if (activeResize) {
        persistWidths(activeResize.table, activeResize.widths)
        document.body.style.cursor = previousCursor.value
        document.body.style.userSelect = previousUserSelect.value
        activeResize = null
        suppressNextClick = true
      }
      pendingResize = null
    }

    const handleMouseMove = (event) => {
      if ((activeResize || pendingResize) && (event.buttons & 1) !== 1) {
        stopResize()
        return
      }

      if (activeResize) {
        const delta = event.clientX - activeResize.startX
        activeResize.widths[activeResize.index] = Math.max(MIN_COLUMN_WIDTH, activeResize.startWidth + delta)
        applyWidths(activeResize.table, activeResize.widths)
        return
      }

      if (pendingResize) {
        const delta = event.clientX - pendingResize.startX
        if (Math.abs(delta) < RESIZE_START_THRESHOLD_PX) return

        const widths = getCurrentWidths(pendingResize.table)
        previousCursor.value = document.body.style.cursor
        previousUserSelect.value = document.body.style.userSelect
        document.body.style.cursor = 'col-resize'
        document.body.style.userSelect = 'none'
        activeResize = {
          ...pendingResize,
          startWidth: widths[pendingResize.index],
          widths,
        }
        activeResize.widths[activeResize.index] = Math.max(MIN_COLUMN_WIDTH, activeResize.startWidth + delta)
        applyWidths(activeResize.table, activeResize.widths)
        return
      }

      document.body.classList.toggle('table-column-resize-cursor', Boolean(findResizableHeader(event)))
    }

    const handleMouseDown = (event) => {
      if (event.button !== 0) return
      const resizableHeader = findResizableHeader(event)
      if (event.detail > 1) {
        if (resizableHeader) {
          event.preventDefault()
          event.stopPropagation()
          suppressNextClick = true
          resetTableWidths(resizableHeader.table)
        }
        return
      }
      if (!resizableHeader) return

      event.preventDefault()
      event.stopPropagation()
      suppressNextClick = true
      pendingResize = {
        ...resizableHeader,
        startX: event.clientX,
      }
    }

    const handleClick = (event) => {
      const shouldSuppress = suppressNextClick || Boolean(findResizableHeader(event))
      suppressNextClick = false
      if (shouldSuppress) {
        event.preventDefault()
        event.stopPropagation()
      }
    }

    const handleDoubleClick = (event) => {
      const resizableHeader = findResizableHeader(event)
      if (!resizableHeader) return
      event.preventDefault()
      event.stopPropagation()
      resetTableWidths(resizableHeader.table)
    }

    const handleMouseLeave = () => {
      if (!activeResize) document.body.classList.remove('table-column-resize-cursor')
    }

    const handleMouseUp = () => stopResize()
    const handleWindowBlur = () => stopResize()

    document.addEventListener('mousemove', handleMouseMove)
    document.addEventListener('mousedown', handleMouseDown, true)
    document.addEventListener('click', handleClick, true)
    document.addEventListener('mouseup', handleMouseUp, true)
    document.addEventListener('pointerup', handleMouseUp, true)
    document.addEventListener('dblclick', handleDoubleClick, true)
    document.addEventListener('mouseleave', handleMouseLeave)
    window.addEventListener('mouseup', handleMouseUp, true)
    window.addEventListener('blur', handleWindowBlur)

    return () => {
      document.removeEventListener('mousemove', handleMouseMove)
      document.removeEventListener('mousedown', handleMouseDown, true)
      document.removeEventListener('click', handleClick, true)
      document.removeEventListener('mouseup', handleMouseUp, true)
      document.removeEventListener('pointerup', handleMouseUp, true)
      document.removeEventListener('dblclick', handleDoubleClick, true)
      document.removeEventListener('mouseleave', handleMouseLeave)
      window.removeEventListener('mouseup', handleMouseUp, true)
      window.removeEventListener('blur', handleWindowBlur)
      document.body.classList.remove('table-column-resize-cursor')
      stopResize()
    }
  }, [])
}
