import { tr } from '../i18n'

export default function SelectionSummary({ count, items = [] }) {
  if (!count) return null

  return (
    <div className="selection-summary">
      <span className="selection-summary-count">{tr('selectedRows')}: {count}</span>
      {items.map((item) => (
        <span key={item.label} className={`selection-summary-item ${item.tone ? `selection-summary-item-${item.tone}` : ''}`.trim()}>
          <span>{item.label}</span>
          <strong>{item.value}</strong>
        </span>
      ))}
    </div>
  )
}
