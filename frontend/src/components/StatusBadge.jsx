const TONE_CLASS = {
  success: 'badge-success',
  warning: 'badge-warning',
  info: 'badge-info',
  danger: 'badge-danger',
  muted: 'badge-muted',
}

export default function StatusBadge({ tone = 'info', className = '', children, title, style }) {
  const toneClass = TONE_CLASS[tone] || TONE_CLASS.info
  return (
    <span className={`badge ${toneClass} ${className}`.trim()} title={title} style={style}>
      {children}
    </span>
  )
}
