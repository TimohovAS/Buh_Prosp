export default function Modal({
  isOpen,
  onClose,
  title,
  children,
  className = '',
  bodyClassName = '',
  maxWidth,
  closeOnOverlay = false,
  style,
  resizable = true,
}) {
  if (!isOpen) return null

  const hasExplicitWidth = !!maxWidth || !!style?.width || !!className
  const modalStyle = {
    ...(resizable && !hasExplicitWidth ? { width: 'min(500px, 90vw)' } : {}),
    ...(maxWidth ? { maxWidth } : {}),
    ...(style || {}),
  }

  return (
    <div className="modal-overlay" onClick={closeOnOverlay ? onClose : undefined}>
      <div
        className={`modal ${resizable ? 'modal-resizable' : ''} ${className}`.trim()}
        style={modalStyle}
        onClick={closeOnOverlay ? (event) => event.stopPropagation() : undefined}
      >
        <div className="modal-header">
          <h3 className="modal-title">{title}</h3>
          <button type="button" className="modal-close" onClick={onClose} aria-label="close">
            &times;
          </button>
        </div>
        <div className={`modal-body ${bodyClassName}`.trim()}>{children}</div>
      </div>
    </div>
  )
}
