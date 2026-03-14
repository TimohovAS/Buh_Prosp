export default function Modal({
  isOpen,
  onClose,
  title,
  children,
  className = '',
  bodyClassName = '',
  maxWidth,
}) {
  if (!isOpen) return null

  return (
    <div className="modal-overlay">
      <div className={`modal ${className}`.trim()} style={maxWidth ? { maxWidth } : undefined}>
        <div className="modal-header">
          <h3 className="modal-title">{title}</h3>
          <button type="button" className="modal-close" onClick={onClose} aria-label="close">
            &times;
          </button>
        </div>
        <div className={`modal-body ${bodyClassName}`.trim()}>
          {children}
        </div>
      </div>
    </div>
  )
}
