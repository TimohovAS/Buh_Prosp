import Modal from './Modal'

export default function EntityDetailModal({
  isOpen,
  onClose,
  title,
  maxWidth = '920px',
  details,
  actions = null,
  children = null,
  className = '',
}) {
  return (
    <Modal isOpen={isOpen} onClose={onClose} title={title} maxWidth={maxWidth} className={className}>
      <div className={`record-detail-grid ${actions ? '' : 'record-detail-grid-single'}`.trim()}>
        <div className="record-detail-card">{details}</div>
        {actions ? <div className="record-detail-card">{actions}</div> : null}
      </div>
      {children ? <div className="record-detail-stack">{children}</div> : null}
    </Modal>
  )
}
