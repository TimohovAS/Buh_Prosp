import DatePickerLib from 'react-datepicker'

/** value и onChange работают со строкой YYYY-MM-DD */
export default function DatePicker({ value, onChange, required, className = '', placeholder, ...props }) {
  const date = value && /^\d{4}-\d{2}-\d{2}$/.test(value) ? new Date(value + 'T12:00:00') : null

  const handleChange = (d) => {
    if (!d) {
      onChange('')
      return
    }
    const y = d.getFullYear()
    const m = String(d.getMonth() + 1).padStart(2, '0')
    const day = String(d.getDate()).padStart(2, '0')
    onChange(`${y}-${m}-${day}`)
  }

  return (
    <DatePickerLib
      selected={date}
      onChange={handleChange}
      dateFormat="dd.MM.yyyy"
      showMonthDropdown
      showYearDropdown
      dropdownMode="select"
      placeholderText={placeholder}
      className={`form-input ${className}`}
      isClearable={!required}
      {...props}
    />
  )
}
