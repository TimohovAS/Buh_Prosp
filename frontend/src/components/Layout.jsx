import { Outlet } from 'react-router-dom'
import { NavLink } from 'react-router-dom'
import { api } from '../api'
import { tr } from '../i18n'

export default function Layout({ lang, toggleLang }) {
  return (
    <div className="app">
      <aside className="sidebar">
        <div style={{ padding: '2rem 1.25rem 1rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <strong style={{ fontSize: '1.25rem' }}>ProspEl <span style={{ fontSize: '0.75rem', opacity: 0.7 }}>v2</span></strong>
          <button
            onClick={toggleLang}
            className="btn btn-sm btn-secondary"
            title={lang === 'sr' ? tr('langRu') : tr('langSr')}
          >
            {lang === 'sr' ? 'RU' : 'SR'}
          </button>
        </div>
        <nav>
          <ul className="sidebar-nav">
            <li><NavLink to="/" end>{tr('dashboard')}</NavLink></li>
            <li><NavLink to="/income">{tr('income')}</NavLink></li>
            <li><NavLink to="/clients">{tr('clients')}</NavLink></li>
            <li><NavLink to="/contracts">{tr('contracts')}</NavLink></li>
            <li><NavLink to="/projects">{tr('projects')}</NavLink></li>
            <li><NavLink to="/expenses">{tr('expenses')}</NavLink></li>
            <li><NavLink to="/planned-expenses">{tr('plannedExpenses')}</NavLink></li>
            <li><NavLink to="/bank-import">{tr('bankImport')}</NavLink></li>
            <li><NavLink to="/finance">{tr('finance')}</NavLink></li>
            <li><NavLink to="/finance/ar">{tr('financeAR')}</NavLink></li>
            <li><NavLink to="/finance/cashflow">{tr('cashflowTitle')}</NavLink></li>
            <li><NavLink to="/payments">{tr('payments')}</NavLink></li>
            <li><NavLink to="/settings">{tr('settings')}</NavLink></li>
          </ul>
        </nav>
        <div style={{ padding: '1rem 1.25rem', marginTop: 'auto' }}>
          <button
            className="btn btn-sm btn-secondary"
            onClick={() => { api.auth.logout(); window.location.href = '/login'; }}
          >
            {tr('logout')}
          </button>
        </div>
      </aside>
      <main className="main">
        <Outlet />
      </main>
    </div>
  )
}
