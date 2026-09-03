import { tr } from '../i18n'

export default function YearFilterSelect({
  value,
  availableYears,
  onChange,
  includeAllTime = true,
  className = 'form-input',
  style = { width: 'auto' },
  title,
  id,
  disabled = false,
}) {
  return (
    <select
      id={id}
      className={className}
      style={style}
      value={value === '' ? '' : String(value)}
      onChange={(event) => onChange(event.target.value ? Number(event.target.value) : '')}
      title={title}
      disabled={disabled}
    >
      {includeAllTime ? <option value="">{tr('allTime')}</option> : null}
      {availableYears.map((optionYear) => (
        <option key={optionYear} value={optionYear}>
          {optionYear}
        </option>
      ))}
    </select>
  )
}
