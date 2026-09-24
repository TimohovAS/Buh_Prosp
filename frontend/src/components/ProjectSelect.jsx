import { Check, ChevronDown, LoaderCircle, Search, X } from 'lucide-react'
import { useEffect, useId, useMemo, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { api } from '../api'
import { tr } from '../i18n'
import { matchesSearch } from '../utils/searchUtils'

const UI_DASH = '\u2014'

export default function ProjectSelect({
  projects,
  value,
  onChange,
  required = false,
  allowEmpty = false,
  emptyLabel = UI_DASH,
  placeholder,
  projectFilter = null,
}) {
  const rootRef = useRef(null)
  const dropdownRef = useRef(null)
  const inputRef = useRef(null)
  const refreshPromiseRef = useRef(null)
  const listboxId = useId()
  const [isOpen, setIsOpen] = useState(false)
  const [search, setSearch] = useState('')
  const [highlightedIndex, setHighlightedIndex] = useState(0)
  const [liveProjects, setLiveProjects] = useState(projects)
  const [isLoading, setIsLoading] = useState(false)
  const [dropdownStyle, setDropdownStyle] = useState(null)

  const normalizedValue = value === null || value === undefined ? '' : String(value)

  useEffect(() => {
    inputRef.current?.setCustomValidity(required && !normalizedValue ? tr('projectRequired') : '')
  }, [normalizedValue, required])

  const visibleProjects = useMemo(
    () => (projectFilter ? projects.filter(projectFilter) : projects),
    [projectFilter, projects]
  )

  useEffect(() => {
    setLiveProjects(visibleProjects)
  }, [visibleProjects])

  const selectedProject = useMemo(
    () => liveProjects.find((project) => String(project.id) === normalizedValue) || null,
    [liveProjects, normalizedValue]
  )

  const filteredOptions = useMemo(() => {
    // Код проекта в выборе не нужен: проект узнают по названию и клиенту
    const items = liveProjects
      .filter((project) => project.status === 'active')
      .filter((project) => matchesSearch(search, project.name, project.client_name))
      .map((project) => ({
        key: `project-${project.id}`,
        value: String(project.id),
        label: project.name,
        description: project.client_name,
        group: project.is_internal ? tr('internalProject') : tr('commercialProject'),
      }))

    if (allowEmpty) items.unshift({ key: 'empty', value: '', label: emptyLabel, group: '' })
    return items
  }, [allowEmpty, emptyLabel, liveProjects, search])

  useEffect(() => {
    if (!isOpen) {
      setSearch('')
      setHighlightedIndex(0)
      setIsLoading(false)
    }
  }, [isOpen])

  useEffect(() => {
    if (highlightedIndex >= filteredOptions.length) {
      setHighlightedIndex(filteredOptions.length > 0 ? filteredOptions.length - 1 : 0)
    }
  }, [filteredOptions.length, highlightedIndex])

  useEffect(() => {
    if (!isOpen || filteredOptions.length === 0) return
    document.getElementById(`${listboxId}-option-${highlightedIndex}`)?.scrollIntoView({ block: 'nearest' })
  }, [filteredOptions.length, highlightedIndex, isOpen, listboxId])

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

  const refreshProjects = async () => {
    if (refreshPromiseRef.current) return refreshPromiseRef.current
    setIsLoading(true)
    const request = api.projects
      .list({ show_inactive: true })
      .then((projectList) => {
        if (Array.isArray(projectList)) {
          setLiveProjects(projectFilter ? projectList.filter(projectFilter) : projectList)
        }
        return projectList
      })
      .catch(() => projects)
      .finally(() => {
        refreshPromiseRef.current = null
        setIsLoading(false)
      })
    refreshPromiseRef.current = request
    return request
  }

  const openDropdown = () => {
    setSearch('')
    const activeProjects = liveProjects.filter((project) => project.status === 'active')
    const selectedIndex = activeProjects.findIndex((project) => String(project.id) === normalizedValue)
    setHighlightedIndex(selectedIndex >= 0 ? selectedIndex + (allowEmpty ? 1 : 0) : 0)
    setIsOpen(true)
    void refreshProjects()
  }

  const commitValue = (nextValue) => {
    onChange(nextValue)
    setIsOpen(false)
  }

  const clearProject = () => {
    onChange('')
    setSearch('')
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
      setHighlightedIndex((previous) => Math.min(previous + 1, Math.max(filteredOptions.length - 1, 0)))
      return
    }
    if (event.key === 'ArrowUp') {
      event.preventDefault()
      setHighlightedIndex((previous) => Math.max(previous - 1, 0))
      return
    }
    if (event.key === 'Enter') {
      event.preventDefault()
      const option = filteredOptions[highlightedIndex]
      if (option) commitValue(option.value)
      return
    }
    if (event.key === 'Escape') {
      event.preventDefault()
      setIsOpen(false)
    }
  }

  const selectedLabel = selectedProject ? selectedProject.name : allowEmpty ? emptyLabel : ''
  const inputValue = isOpen ? search : selectedLabel

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
        placeholder={placeholder || tr('projectSearchPlaceholder')}
        autoComplete="off"
        role="combobox"
        aria-autocomplete="list"
        aria-controls={listboxId}
        aria-expanded={isOpen}
        aria-label={tr('project')}
        aria-required={required}
        required={required}
        aria-activedescendant={
          isOpen && filteredOptions.length ? `${listboxId}-option-${highlightedIndex}` : undefined
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
            onClick={clearProject}
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
          aria-label={tr('project')}
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
              aria-label={tr('project')}
            >
              {filteredOptions.length === 0 ? (
                <div className="searchable-select-empty">{tr('projectSearchNoResults')}</div>
              ) : (
                filteredOptions.map((option, index) => {
                  const previous = filteredOptions[index - 1]
                  const showGroup = option.group && option.group !== previous?.group
                  const isSelected = option.value === normalizedValue
                  const isHighlighted = index === highlightedIndex
                  return (
                    <div key={option.key}>
                      {showGroup ? <div className="searchable-select-group">{option.group}</div> : null}
                      <button
                        id={`${listboxId}-option-${index}`}
                        type="button"
                        className={`searchable-select-option${
                          isHighlighted ? ' is-highlighted' : ''
                        }${isSelected ? ' is-selected' : ''}`}
                        role="option"
                        aria-selected={isSelected}
                        onMouseEnter={() => setHighlightedIndex(index)}
                        onMouseDown={(event) => event.preventDefault()}
                        onClick={() => commitValue(option.value)}
                      >
                        {option.description ? (
                          <span className="searchable-select-option-copy">
                            <span>{option.label}</span>
                            <span className="searchable-select-option-description">{option.description}</span>
                          </span>
                        ) : (
                          <span>{option.label}</span>
                        )}
                        {isSelected ? <Check aria-hidden="true" size={16} /> : null}
                      </button>
                    </div>
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
