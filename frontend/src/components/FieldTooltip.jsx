import { CircleHelp } from 'lucide-react'

export default function FieldTooltip({ text, align = 'left' }) {
  if (!text) return null

  return (
    <span className={`field-tooltip field-tooltip-align-${align}`} tabIndex={0} aria-label={text}>
      <CircleHelp className="field-tooltip-trigger" size={15} aria-hidden="true" />
      <span className="field-tooltip-bubble" role="tooltip">
        {text}
      </span>
    </span>
  )
}
