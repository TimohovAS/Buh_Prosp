const UI_CLEAR = '\u00D7'

export default function SearchInput({
  value,
  onChange,
  placeholder,
  style,
  className = 'form-input',
  ...props
}) {
  return (
    <div className="search-input-wrap" style={style}>
      <input
        type="text"
        className={className}
        placeholder={placeholder}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        {...props}
      />
      {value ? (
        <button type="button" className="search-input-clear" onClick={() => onChange('')} aria-label="clear">
          {UI_CLEAR}
        </button>
      ) : null}
    </div>
  )
}
