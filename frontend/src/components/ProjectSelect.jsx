import { useEffect, useMemo, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { api } from '../api'
import { tr } from '../i18n'

const UI_DASH = '\u2014'

function buildProjectLabel(project) {
  if (!project) return ''
  return project.code ? `${project.name} ${UI_DASH} ${project.code}` : project.name
}

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
  const refreshPromiseRef = useRef(null)
  const [isOpen, setIsOpen] = useState(false)
  const [search, setSearch] = useState('')
  const [highlightedIndex, setHighlightedIndex] = useState(0)
  const [liveProjects, setLiveProjects] = useState(projects)
  const [dropdownStyle, setDropdownStyle] = useState(null)

  const visibleProjects = useMemo(
    () => (projectFilter ? projects.filter(projectFilter) : projects),
    [projectFilter, projects]
  )

  useEffect(() => {
    setLiveProjects(visibleProjects)
  }, [visibleProjects])

  const selectedProject = useMemo(
    () => liveProjects.find((project) => String(project.id) === String(value)) || null,
    [liveProjects, value]
  )

  const selectedLabel = selectedProject ? buildProjectLabel(selectedProject) : allowEmpty ? emptyLabel : ''
  const inputValue = isOpen ? search : selectedLabel

  const filteredOptions = useMemo(() => {
    const normalizedSearch = (search || '').trim().toLowerCase()
    const items = liveProjects
      .filter((project) => project.status !== 'archived')
      .filter((project) => {
        if (!normalizedSearch) return true
        return (
          (project.name || '').toLowerCase().includes(normalizedSearch) ||
          (project.code || '').toLowerCase().includes(normalizedSearch)
        )
      })
      .map((project) => ({
        key: `project-${project.id}`,
        value: String(project.id),
        label: buildProjectLabel(project),
        group: project.is_internal ? tr('internalProject') : tr('commercialProject'),
      }))

    if (allowEmpty) {
      items.unshift({ key: 'empty', value: '', label: emptyLabel, group: '' })
    }

    return items
  }, [allowEmpty, emptyLabel, liveProjects, search])

  useEffect(() => {
    if (!isOpen) {
      setSearch('')
      setHighlightedIndex(0)
    }
  }, [isOpen])

  useEffect(() => {
    const handleClickOutside = (event) => {
      if (!rootRef.current?.contains(event.target) && !dropdownRef.current?.contains(event.target)) {
        setIsOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  useEffect(() => {
    if (!isOpen) return undefined

    const updateDropdownPosition = () => {
      const rect = rootRef.current?.getBoundingClientRect()
      if (!rect) return
      const gap = 4
      const viewportPadding = 12
      const spaceBelow = window.innerHeight - rect.bottom - viewportPadding
      const spaceAbove = rect.top - viewportPadding
      const openUp = spaceBelow < 180 && spaceAbove > spaceBelow
      const maxHeight = Math.max(140, Math.min(320, (openUp ? spaceAbove : spaceBelow) - gap))
      setDropdownStyle({
        position: 'fixed',
        top: openUp ? undefined : rect.bottom + gap,
        bottom: openUp ? window.innerHeight - rect.top + gap : undefined,
        left: rect.left,
        width: rect.width,
        zIndex: 3000,
        background: 'var(--color-surface)',
        border: '1px solid rgba(255,255,255,0.08)',
        borderRadius: 12,
        boxShadow: '0 10px 30px rgba(0,0,0,0.25)',
        maxHeight,
        overflowY: 'auto',
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

  useEffect(() => {
    if (highlightedIndex >= filteredOptions.length) {
      setHighlightedIndex(filteredOptions.length > 0 ? filteredOptions.length - 1 : 0)
    }
  }, [filteredOptions.length, highlightedIndex])

  const commitValue = (nextValue) => {
    onChange(nextValue)
    setIsOpen(false)
  }

  const refreshProjects = async () => {
    if (refreshPromiseRef.current) {
      return refreshPromiseRef.current
    }
    const request = api.projects
      .list({ show_archived: true })
      .then((projectList) => {
        if (Array.isArray(projectList)) {
          setLiveProjects(projectFilter ? projectList.filter(projectFilter) : projectList)
        }
        return projectList
      })
      .catch(() => projects)
      .finally(() => {
        refreshPromiseRef.current = null
      })
    refreshPromiseRef.current = request
    return request
  }

  const handleFocus = () => {
    setIsOpen(true)
    setSearch('')
    void refreshProjects()
  }

  const handleKeyDown = (event) => {
    if (!isOpen && (event.key === 'ArrowDown' || event.key === 'Enter')) {
      event.preventDefault()
      setIsOpen(true)
      void refreshProjects()
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

  return (
    <div ref={rootRef} style={{ position: 'relative' }}>
      <input
        type="text"
        className="form-input"
        value={inputValue}
        onFocus={handleFocus}
        onChange={(event) => {
          setSearch(event.target.value)
          setIsOpen(true)
          setHighlightedIndex(0)
        }}
        onKeyDown={handleKeyDown}
        placeholder={placeholder || `${tr('search')}: ${tr('project')}`}
        autoComplete="off"
        aria-label={tr('project')}
        aria-expanded={isOpen}
        aria-required={required}
      />
      {isOpen &&
        dropdownStyle &&
        createPortal(
          <div ref={dropdownRef} style={dropdownStyle}>
            {filteredOptions.length === 0 ? (
              <div style={{ padding: '0.75rem', color: 'var(--color-text-muted)', fontSize: '0.875rem' }}>
                {tr('noRecords')}
              </div>
            ) : (
              filteredOptions.map((option, index) => {
                const previous = filteredOptions[index - 1]
                const showGroup = option.group && option.group !== previous?.group
                return (
                  <div key={option.key}>
                    {showGroup && (
                      <div
                        style={{
                          padding: '0.5rem 0.75rem 0.25rem',
                          fontSize: '0.72rem',
                          fontWeight: 700,
                          color: 'var(--color-text-muted)',
                          textTransform: 'uppercase',
                        }}
                      >
                        {option.group}
                      </div>
                    )}
                    <button
                      type="button"
                      onMouseDown={(event) => event.preventDefault()}
                      onClick={() => commitValue(option.value)}
                      style={{
                        width: '100%',
                        textAlign: 'left',
                        border: 'none',
                        background: index === highlightedIndex ? 'rgba(59,130,246,0.16)' : 'transparent',
                        color: 'var(--color-text)',
                        padding: '0.65rem 0.75rem',
                        cursor: 'pointer',
                      }}
                    >
                      {option.label}
                    </button>
                  </div>
                )
              })
            )}
          </div>,
          document.body
        )}
    </div>
  )
}
