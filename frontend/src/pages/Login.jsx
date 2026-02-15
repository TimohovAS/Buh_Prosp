import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api'
import { tr } from '../i18n'

export default function Login({ onLoginSuccess }) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const navigate = useNavigate()

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      const data = await api.auth.login(username, password)
      onLoginSuccess?.(data)
      navigate('/')
    } catch (err) {
      setError(err.message || tr('loginError'))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{
      minHeight: '100vh',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      background: 'var(--color-bg)',
    }}>
      <div className="card" style={{ maxWidth: 360, width: '100%' }}>
        <h1 style={{ margin: '0 0 1.5rem 0', fontSize: '1.25rem' }}>ProspEl</h1>
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
          {error && <p style={{ color: 'var(--color-danger)', marginBottom: '1rem', fontSize: '0.875rem' }}>{error}</p>}
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
