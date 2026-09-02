import { Check, ChevronDown, LoaderCircle, Search, X } from 'lucide-react'
import { useEffect, useId, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { api } from '../api'
import { tr } from '../i18n'

const SEARCH_DELAY_MS = 220

export default function ClientSelect({ clients, value, onChange, onSelect, required = false, placeholder }) {
  const rootRef = useRef(null)
  const dropdownRef = useRef(null)
  const inputRef = useRef(null)
  const searchRequestRef = useRef(0)
  const listboxId = useId()
  const [isOpen, setIsOpen] = useState(false)
  const [search, setSearch] = useState('')
  const [options, setOptions] = useState(clients)
  const [selectedClient, setSelectedClient] = useState(null)
  const [highlightedIndex, setHighlightedIndex] = useState(0)
  const [isLoading, setIsLoading] = useState(false)
  const [dropdownStyle, setDropdownStyle] = useState(null)

  const normalizedValue = value === null || value === undefined ? '' : String(value)

  useEffect(() => {
    inputRef.current?.setCustomValidity(required && !normalizedValue ? tr('selectClient') : '')
  }, [normalizedValue, required])

  useEffect(() => {
    if (!isOpen) setOptions(clients)
  }, [clients, isOpen])

  useEffect(() => {
    if (!normalizedValue) {
      setSelectedClient(null)
      return undefined
    }

    const existingClient = clients.find((client) => String(client.id) === normalizedValue)
    if (existingClient) {
      setSelectedClient(existingClient)
      return undefined
    }

    setSelectedClient(null)
    let isCurrent = true
    api.clients
      .get(normalizedValue)
      .then((client) => {
        if (isCurrent) setSelectedClient(client)
      })
      .catch(() => {
        if (isCurrent) setSelectedClient(null)
      })
    return () => {
      isCurrent = false
    }
  }, [clients, normalizedValue])

  useEffect(() => {
    if (!isOpen) {
      setSearch('')
      setHighlightedIndex(0)
      setIsLoading(false)
      return undefined
    }

    const query = search.trim()
    if (!query) {
      searchRequestRef.current += 1
      setOptions(clients)
      setIsLoading(false)
      return undefined
    }

    const requestId = searchRequestRef.current + 1
    searchRequestRef.current = requestId
    const normalizedQuery = query.toLocaleLowerCase()
    setOptions(clients.filter((client) => client.name?.toLocaleLowerCase().includes(normalizedQuery)))
    setIsLoading(true)
    const timeoutId = window.setTimeout(() => {
      api.clients
        .listBrief(query)
        .then((clientList) => {
          if (searchRequestRef.current === requestId) {
            setOptions(Array.isArray(clientList) ? clientList : [])
          }
        })
        .catch(() => {
          if (searchRequestRef.current === requestId) setOptions([])
        })
        .finally(() => {
          if (searchRequestRef.current === requestId) setIsLoading(false)
        })
    }, SEARCH_DELAY_MS)

    return () => window.clearTimeout(timeoutId)
  }, [clients, isOpen, search])

  const visibleOptions = options

  useEffect(() => {
    if (highlightedIndex >= visibleOptions.length) {
      setHighlightedIndex(visibleOptions.length > 0 ? visibleOptions.length - 1 : 0)
    }
  }, [highlightedIndex, visibleOptions.length])

  useEffect(() => {
    if (!isOpen || visibleOptions.length === 0) return
    document.getElementById(`${listboxId}-option-${highlightedIndex}`)?.scrollIntoView({ block: 'nearest' })
  }, [highlightedIndex, isOpen, listboxId, visibleOptions.length])

  useEffect(() => {
    const handleClickOutside = (event) => {
      if (!rootRef.current?.contains(event.target) && !dropdownRef.current?.contains(event.target)) {
        setIsOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    document.addEventListener('focusin', handleClickOutside)
    return () => {
      document.removeEventListener('mousedown', handleClickOutside)
      document.removeEventListener('focusin', handleClickOutside)
    }
  }, [])

  useEffect(() => {
    if (!isOpen) return undefined

    const updateDropdownPosition = () => {
      const rect = rootRef.current?.getBoundingClientRect()
      if (!rect) return
      const gap = 6
      const viewportPadding = 12
      const spaceBelow = window.innerHeight - rect.bottom - viewportPadding
      const spaceAbove = rect.top - viewportPadding
      const openUp = spaceBelow < 220 && spaceAbove > spaceBelow
      const maxHeight = Math.max(160, Math.min(340, (openUp ? spaceAbove : spaceBelow) - gap))
      setDropdownStyle({
        position: 'fixed',
        top: openUp ? undefined : rect.bottom + gap,
        bottom: openUp ? window.innerHeight - rect.top + gap : undefined,
        left: rect.left,
        width: rect.width,
        maxHeight,
        zIndex: 3000,
      })
    }

    updateDropdownPosition()
    window.addEventListener('resize', updateDropdownPosition)
    window.addEventListener('scroll', updateDropdownPosition, true)
    return () => {
      window.removeEventListener('resize', updateDropdownPosition)
      window.removeEventListener('scroll', updateDropdownPosition, true)
    }
  }, [isOpen])

  const openDropdown = () => {
    setSearch('')
    setOptions(clients)
    const selectedIndex = clients.findIndex((client) => String(client.id) === normalizedValue)
    setHighlightedIndex(selectedIndex >= 0 ? selectedIndex : 0)
    setIsOpen(true)
  }

  const commitClient = (client) => {
    setSelectedClient(client)
    onChange(String(client.id))
    onSelect?.(client)
    setIsOpen(false)
  }

  const clearClient = () => {
    setSelectedClient(null)
    onChange('')
    onSelect?.(null)
    setSearch('')
    setOptions(clients)
    setHighlightedIndex(0)
  }

  const handleKeyDown = (event) => {
    if (!isOpen && (event.key === 'ArrowDown' || event.key === 'Enter')) {
      event.preventDefault()
      openDropdown()
      return
    }
    if (!isOpen) return

    if (event.key === 'ArrowDown') {
      event.preventDefault()
      setHighlightedIndex((previous) => Math.min(previous + 1, Math.max(visibleOptions.length - 1, 0)))
      return
    }
    if (event.key === 'ArrowUp') {
      event.preventDefault()
      setHighlightedIndex((previous) => Math.max(previous - 1, 0))
      return
    }
    if (event.key === 'Enter') {
      event.preventDefault()
      const client = visibleOptions[highlightedIndex]
      if (client) commitClient(client)
      return
    }
    if (event.key === 'Escape') {
      event.preventDefault()
      setIsOpen(false)
    }
  }

  const inputValue = isOpen ? search : selectedClient?.name || ''

  return (
    <div ref={rootRef} className={`searchable-select${isOpen ? ' is-open' : ''}`}>
      <Search aria-hidden="true" className="searchable-select-search-icon" size={15} />
      <input
        ref={inputRef}
        type="text"
        className="form-input searchable-select-input"
        value={inputValue}
        onFocus={() => {
          if (!isOpen) openDropdown()
        }}
        onChange={(event) => {
          setSearch(event.target.value)
          setHighlightedIndex(0)
          setIsOpen(true)
        }}
        onKeyDown={handleKeyDown}
        placeholder={placeholder || tr('clientSearchPlaceholder')}
        autoComplete="off"
        role="combobox"
        aria-autocomplete="list"
        aria-controls={listboxId}
        aria-expanded={isOpen}
        aria-label={tr('client')}
        aria-required={required}
        required={required}
        aria-activedescendant={
          isOpen && visibleOptions.length ? `${listboxId}-option-${highlightedIndex}` : undefined
        }
      />
      <div className="searchable-select-actions">
        {isLoading ? (
          <LoaderCircle aria-hidden="true" className="searchable-select-spinner" size={15} />
        ) : null}
        {!isLoading && normalizedValue ? (
          <button
            type="button"
            className="searchable-select-icon-button"
            onMouseDown={(event) => event.preventDefault()}
            onClick={clearClient}
            title={tr('clearSelection')}
            aria-label={tr('clearSelection')}
          >
            <X size={14} />
          </button>
        ) : null}
        <button
          type="button"
          className="searchable-select-icon-button"
          onMouseDown={(event) => event.preventDefault()}
          onClick={() => (isOpen ? setIsOpen(false) : openDropdown())}
          tabIndex={-1}
          aria-label={tr('selectClient')}
        >
          <ChevronDown aria-hidden="true" className="searchable-select-chevron" size={15} />
        </button>
      </div>

      {isOpen && dropdownStyle
        ? createPortal(
            <div
              ref={dropdownRef}
              id={listboxId}
              className="searchable-select-dropdown"
              style={dropdownStyle}
              role="listbox"
              aria-label={tr('client')}
            >
              {visibleOptions.length === 0 ? (
                <div className="searchable-select-empty">
                  {isLoading ? tr('loading') : tr('clientSearchNoResults')}
                </div>
              ) : (
                visibleOptions.map((client, index) => {
                  const isSelected = String(client.id) === normalizedValue
                  const isHighlighted = index === highlightedIndex
                  return (
                    <button
                      key={client.id}
                      id={`${listboxId}-option-${index}`}
                      type="button"
                      className={`searchable-select-option${isHighlighted ? ' is-highlighted' : ''}${
                        isSelected ? ' is-selected' : ''
                      }`}
                      role="option"
                      aria-selected={isSelected}
                      onMouseEnter={() => setHighlightedIndex(index)}
                      onMouseDown={(event) => event.preventDefault()}
                      onClick={() => commitClient(client)}
                    >
                      <span>{client.name}</span>
                      {isSelected ? <Check aria-hidden="true" size={16} /> : null}
                    </button>
                  )
                })
              )}
            </div>,
            document.body
          )
        : null}
    </div>
  )
}
