import { useState } from 'react'
import { Building2 } from 'lucide-react'
import { api } from '../api'
import { tr } from '../i18n'
import { useEnterpriseBrand } from '../hooks/useEnterpriseBrand'

export default function Login({ onLoginSuccess }) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const brand = useEnterpriseBrand()
  const enterpriseName = brand.name && brand.name !== 'ProspEl' ? brand.name : ''

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      const data = await api.auth.login(username, password)
      onLoginSuccess?.(data)
      // Загружаем актуальную сборку целиком. Это важно, если экран входа был
      // открыт во время обновления и его старые lazy chunks уже удалены.
      window.location.replace('/')
    } catch (err) {
      setError(err.message || tr('loginError'))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div
      style={{
        minHeight: '100vh',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        background: 'var(--color-bg)',
      }}
    >
      <div className="card" style={{ maxWidth: 380, width: '100%' }}>
        <div className="login-brand">
          <div className="brand-mark brand-mark-lg" aria-hidden="true">
            {brand.emblem_data_url ? <img src={brand.emblem_data_url} alt="" /> : <Building2 size={28} />}
          </div>
          <div className="login-brand-copy">
            <h1 style={{ margin: 0, fontSize: '1.35rem' }}>ProspEl</h1>
            {enterpriseName ? (
              <p style={{ margin: '0.25rem 0 0 0', color: 'var(--color-text-muted)', fontSize: '0.875rem' }}>
                {enterpriseName}
              </p>
            ) : null}
          </div>
        </div>
        <p style={{ color: 'var(--color-text-muted)', marginBottom: '1.5rem', fontSize: '0.875rem' }}>
          {tr('login')}
        </p>
        <form onSubmit={handleSubmit}>
          <div className="form-group">
            <label className="form-label">{tr('username')}</label>
            <input
              type="text"
              className="form-input"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              required
              autoFocus
            />
          </div>
          <div className="form-group">
            <label className="form-label">{tr('password')}</label>
            <input
              type="password"
              className="form-input"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
          </div>
          {error && (
            <p style={{ color: 'var(--color-danger)', marginBottom: '1rem', fontSize: '0.875rem' }}>
              {error}
            </p>
          )}
          <button type="submit" className="btn btn-primary" style={{ width: '100%' }} disabled={loading}>
            {loading ? '...' : tr('login')}
          </button>
        </form>
        <p style={{ marginTop: '1rem', fontSize: '0.75rem', color: 'var(--color-text-muted)' }}>
          {tr('loginHint')}
        </p>
      </div>
    </div>
  )
}
