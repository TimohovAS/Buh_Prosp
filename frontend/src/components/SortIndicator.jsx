import { UI_SORT_ASC, UI_SORT_BOTH, UI_SORT_DESC } from '../utils/formatters'

export default function SortIndicator({ active = false, asc = true, style = undefined, className = '' }) {
  return (
    <span
      className={className}
      style={{ marginLeft: 4, opacity: active ? 1 : 0.3, ...(style || {}) }}
      aria-hidden="true"
    >
      {active ? (asc ? UI_SORT_ASC : UI_SORT_DESC) : UI_SORT_BOTH}
    </span>
  )
}
