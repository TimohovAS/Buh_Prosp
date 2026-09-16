import { GripVertical } from 'lucide-react'
import { tr } from '../i18n'

export default function ItemDragHandle({ number, ...props }) {
  const label = tr('moveLine', { number })
  return (
    <div className="item-reorder-start">
      <button
        type="button"
        className="item-reorder-handle"
        aria-label={label}
        aria-keyshortcuts="ArrowUp ArrowDown"
        title={label}
        {...props}
      >
        <GripVertical size={16} aria-hidden="true" />
      </button>
      <span className="item-reorder-number">{number}</span>
    </div>
  )
}
