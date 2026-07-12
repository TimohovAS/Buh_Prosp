import { useEffect, useMemo, useRef, useState } from 'react'
import { ChevronDown, X } from 'lucide-react'

export default function MultiSelect({
  options,
  value,
  onChange,
  placeholder,
  emptyText,
  clearLabel,
  ariaLabel,
  className = '',
}) {
  const [open, setOpen] = useState(false)
  const rootRef = useRef(null)
  const selectedValues = useMemo(() => new Set(value), [value])
  const selectedOptions = useMemo(
    () => options.filter((option) => selectedValues.has(option.value)),
    [options, selectedValues]
  )

  useEffect(() => {
    if (!open) return undefined

    const closeOnOutsideClick = (event) => {
      if (!rootRef.current?.contains(event.target)) setOpen(false)
    }
    const closeOnEscape = (event) => {
      if (event.key === 'Escape') setOpen(false)
    }

    document.addEventListener('mousedown', closeOnOutsideClick)
    document.addEventListener('keydown', closeOnEscape)
    return () => {
      document.removeEventListener('mousedown', closeOnOutsideClick)
      document.removeEventListener('keydown', closeOnEscape)
    }
  }, [open])

  const toggleOption = (optionValue) => {
    onChange(
      selectedValues.has(optionValue)
        ? value.filter((selectedValue) => selectedValue !== optionValue)
        : [...value, optionValue]
    )
  }

  return (
    <div className={`multi-select ${className}`.trim()} ref={rootRef}>
      <button
        type="button"
        className={`form-input multi-select-trigger ${open ? 'is-open' : ''}`.trim()}
        aria-label={ariaLabel}
        aria-haspopup="listbox"
        aria-expanded={open}
        onClick={() => setOpen((previous) => !previous)}
      >
        <span className={`multi-select-value ${selectedOptions.length ? '' : 'is-placeholder'}`.trim()}>
          {selectedOptions.length ? selectedOptions.map((option) => option.label).join(', ') : placeholder}
        </span>
        {selectedOptions.length > 1 ? (
          <span className="multi-select-count">{selectedOptions.length}</span>
        ) : null}
        <ChevronDown className="multi-select-chevron" size={17} />
      </button>

      {open ? (
        <div className="multi-select-menu" role="listbox" aria-multiselectable="true">
          {selectedOptions.length ? (
            <button type="button" className="multi-select-clear" onClick={() => onChange([])}>
              <X size={14} /> {clearLabel}
            </button>
          ) : null}
          <div className="multi-select-options">
            {options.length ? (
              options.map((option) => (
                <label className="multi-select-option" key={option.value}>
                  <input
                    type="checkbox"
                    checked={selectedValues.has(option.value)}
                    onChange={() => toggleOption(option.value)}
                  />
                  <span>{option.label}</span>
                </label>
              ))
            ) : (
              <span className="multi-select-empty">{emptyText}</span>
            )}
          </div>
        </div>
      ) : null}
    </div>
  )
}
