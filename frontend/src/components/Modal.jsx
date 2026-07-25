export default function Modal({
  isOpen,
  onClose,
  title,
  children,
  className = '',
  bodyClassName = '',
  maxWidth,
  style,
  resizable = true,
}) {
  if (!isOpen) return null

  const hasExplicitWidth = !!maxWidth || !!style?.width || !!className
  const modalStyle = {
    ...(resizable && !hasExplicitWidth ? { width: 'min(500px, 90vw)' } : {}),
    // Для ресайзабельной модалки maxWidth — начальная ширина, а не потолок:
    // жёсткий inline max-width не давал растягивать окно мышью шире начального.
    ...(maxWidth ? (resizable ? { width: `min(${maxWidth}, 94vw)` } : { maxWidth }) : {}),
    ...(style || {}),
  }

  // Клик по фону намеренно не закрывает окно: в формах учёта это приводило
  // к потере введённых данных. Закрыть можно крестиком или кнопкой отмены.
  return (
    <div className="modal-overlay">
      <div className={`modal ${resizable ? 'modal-resizable' : ''} ${className}`.trim()} style={modalStyle}>
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
