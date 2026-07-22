import { tr } from '../i18n'

export default function SelectionSummary({
  count,
  items = [],
  actions = null,
  onClear = null,
  countLabel = tr('selectedRows'),
  clearLabel = tr('clearSelection'),
}) {
  if (!count) return null

  return (
    <div className="selection-summary no-print" aria-live="polite">
      <span className="selection-summary-count">
        {countLabel}: <strong>{count}</strong>
      </span>
      {items.map((item) => (
        <span
          key={item.label}
          className={`selection-summary-item ${item.tone ? `selection-summary-item-${item.tone}` : ''}`.trim()}
        >
          <span>{item.label}</span>
          <strong>{item.value}</strong>
        </span>
      ))}
      {actions || onClear ? (
        <div className="selection-summary-actions">
          {actions}
          {onClear ? (
            <button type="button" className="btn btn-sm btn-secondary" onClick={onClear}>
              {clearLabel}
            </button>
          ) : null}
        </div>
      ) : null}
    </div>
  )
}
