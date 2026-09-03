import Modal from './Modal'

export default function EntityDetailModal({
  isOpen,
  onClose,
  onBack,
  backLabel,
  title,
  headerExtra = null,
  maxWidth = '920px',
  details,
  actions = null,
  children = null,
  className = '',
}) {
  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      onBack={onBack}
      backLabel={backLabel}
      title={title}
      headerExtra={headerExtra}
      maxWidth={maxWidth}
      className={className}
    >
      <div className={`record-detail-grid ${actions ? '' : 'record-detail-grid-single'}`.trim()}>
        <div className="record-detail-card">{details}</div>
        {actions ? <div className="record-detail-card">{actions}</div> : null}
      </div>
      {children ? <div className="record-detail-stack">{children}</div> : null}
    </Modal>
  )
}
