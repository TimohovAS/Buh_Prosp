export default function PageHeader({ title, subtitle = null, actions = null, children = null }) {
  return (
    <div className="page-header">
      <div className="page-header-main">
        <h1 className="page-title">{title}</h1>
        {subtitle ? <p className="page-subtitle">{subtitle}</p> : null}
      </div>
      {actions || children ? (
        <div className="page-header-actions">
          {actions}
          {children}
        </div>
      ) : null}
    </div>
  )
}
