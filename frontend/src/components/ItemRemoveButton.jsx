import { Trash2 } from 'lucide-react'
import { tr } from '../i18n'

export default function ItemRemoveButton({ number, className = '', ...props }) {
  const label = tr('removeLine', { number })
  return (
    <button
      type="button"
      className={`btn btn-danger item-editor-remove ${className}`.trim()}
      aria-label={label}
      title={label}
      {...props}
    >
      <Trash2 size={16} aria-hidden="true" />
    </button>
  )
}
