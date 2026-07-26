// Кнопка выбора файла в стиле приложения: нативный input скрыт под label,
// потому что системный контрол выбивается из оформления остальных экранов.
export default function FileInput({
  label,
  accept,
  multiple = false,
  disabled = false,
  onChange,
  selectedName = '',
  buttonClassName = 'btn btn-secondary',
}) {
  return (
    <div className={`file-input${disabled ? ' file-input-disabled' : ''}`}>
      <label className={buttonClassName}>
        {label}
        <input type="file" accept={accept} multiple={multiple} disabled={disabled} onChange={onChange} />
      </label>
      {selectedName ? <span className="file-input-name">{selectedName}</span> : null}
    </div>
  )
}
