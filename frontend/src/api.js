// В dev — через proxy Vite (чтобы избежать CORS и Failed to fetch)
const API_BASE = '/api';

let token = null;

export function setToken(t) {
  token = t;
  if (t) localStorage.setItem('prospel_token', t);
  else localStorage.removeItem('prospel_token');
}

export function setUser(u) {
  if (u) localStorage.setItem('prospel_user', JSON.stringify(u));
  else localStorage.removeItem('prospel_user');
}

export function getUser() {
  try {
    const s = localStorage.getItem('prospel_user');
    return s ? JSON.parse(s) : null;
  } catch {
    return null;
  }
}

export function getToken() {
  if (!token) token = localStorage.getItem('prospel_token');
  return token;
}

async function request(endpoint, options = {}) {
  const headers = {
    'Content-Type': 'application/json',
    ...options.headers,
  };
  const t = getToken();
  if (t) headers['Authorization'] = `Bearer ${t}`;

  const res = await fetch(API_BASE + endpoint, {
    ...options,
    headers,
  });

  if (res.status === 401) {
    setToken(null);
    setUser(null);
    window.location.href = '/login';
    throw new Error('Unauthorized');
  }

  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    const msg = typeof err.detail === 'string' ? err.detail : (Array.isArray(err.detail) ? err.detail.map(e => e.msg).join(', ') : err.message || `HTTP ${res.status}`);
    const e = new Error(msg);
    e.status = res.status;
    throw e;
  }

  const contentType = res.headers.get('content-type');
  if (contentType && contentType.includes('application/json')) {
    return res.json();
  }
  return res;
}

export const api = {
  auth: {
    login: (username, password) => {
      const params = new URLSearchParams();
      params.append('username', username);
      params.append('password', password);
      return fetch(API_BASE + '/auth/login', {
        method: 'POST',
        body: params,
        headers: { Accept: 'application/json' },
      }).then(async (r) => {
        if (!r.ok) {
          const e = await r.json().catch(() => ({}));
          throw new Error(e.detail || 'Неверный логин или пароль');
        }
        const data = await r.json();
        setToken(data.access_token);
        setUser(data.user);
        return data;
      });
    },
    logout: () => { setToken(null); setUser(null); },
    updateMe: (data) => request('/auth/me', { method: 'PATCH', body: JSON.stringify(data) }),
  },

  users: {
    list: (includeInactive) => request(`/users?include_inactive=${includeInactive || false}`),
    get: (id) => request(`/users/${id}`),
    create: (data) => request('/users', { method: 'POST', body: JSON.stringify(data) }),
    update: (id, data) => request(`/users/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
    deactivate: (id) => request(`/users/${id}`, { method: 'DELETE' }),
  },

  income: {
    list: (params) => {
      const q = new URLSearchParams(params).toString();
      return request(`/income?${q}`);
    },
    get: (id) => request(`/income/${id}`),
    create: (data) => request('/income', { method: 'POST', body: JSON.stringify(data) }),
    update: (id, data) => request(`/income/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
    markPaid: (id, data) => request(`/income/${id}/mark-paid`, { method: 'PATCH', body: JSON.stringify(data) }),
    markUnpaid: (id) => request(`/income/${id}/mark-unpaid`, { method: 'PATCH' }),
    delete: (id) => request(`/income/${id}`, { method: 'DELETE' }),
    bulkAssignProject: (data) => request('/income/bulk-assign-project', { method: 'POST', body: JSON.stringify(data) }),
    nextInvoice: (year) => request(`/income/next-invoice-number?year=${year || new Date().getFullYear()}`),
    checkInvoice: (invoiceNumber, year) => request(`/income/check-invoice?invoice_number=${encodeURIComponent(invoiceNumber)}&year=${year || new Date().getFullYear()}`),
  },

  finance: {
    summary: (params) => {
      const q = new URLSearchParams(params).toString();
      return request(`/finance/summary?${q}`);
    },
    ar: () => request('/finance/ar'),
    cashflow: (params) => {
      const q = new URLSearchParams(params).toString();
      return request(`/finance/cashflow?${q}`);
    },
    byProject: (params) => {
      const q = new URLSearchParams(params).toString();
      return request(`/finance/by-project?${q}`);
    },
  },
  projects: {
    list: (params = {}) => {
      const q = new URLSearchParams(params).toString()
      return request(`/projects?${q}`)
    },
    get: (id) => request(`/projects/${id}`),
    create: (data) => request('/projects', { method: 'POST', body: JSON.stringify(data) }),
    update: (id, data) => request(`/projects/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
    delete: (id) => request(`/projects/${id}`, { method: 'DELETE' }),
  },

  contracts: {
    list: (params) => {
      const q = new URLSearchParams(params || {}).toString();
      return request(`/contracts?${q}`);
    },
    get: (id) => request(`/contracts/${id}`),
    create: (data) => request('/contracts/create', { method: 'POST', body: JSON.stringify(data) }),
    update: (id, data) => request(`/contracts/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
    delete: (id) => request(`/contracts/${id}`, { method: 'DELETE' }),
    nextNumber: (year) => request(`/contracts/next-number/?year=${year ?? new Date().getFullYear()}`),
  },

  clients: {
    list: (params) => {
      const q = new URLSearchParams(params).toString();
      return request(`/clients?${q}`);
    },
    listBrief: (search) => request(`/clients/brief?search=${encodeURIComponent(search || '')}`),
    get: (id) => request(`/clients/${id}`),
    create: (data) => request('/clients', { method: 'POST', body: JSON.stringify(data) }),
    update: (id, data) => request(`/clients/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
    delete: (id) => request(`/clients/${id}`, { method: 'DELETE' }),
  },

  expenses: {
    list: (params) => {
      const q = new URLSearchParams(params).toString();
      return request(`/expenses?${q}`);
    },
    get: (id) => request(`/expenses/${id}`),
    create: (data) => request('/expenses', { method: 'POST', body: JSON.stringify(data) }),
    update: (id, data) => request(`/expenses/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
    reverse: (id, data) => request(`/expenses/${id}/reverse`, { method: 'PATCH', body: JSON.stringify(data || {}) }),
    bulkAssignProject: (data) => request('/expenses/bulk-assign-project', { method: 'POST', body: JSON.stringify(data) }),
    delete: (id) => request(`/expenses/${id}`, { method: 'DELETE' }),
  },

  plannedExpenses: {
    list: (params) => {
      const q = new URLSearchParams(params || {}).toString();
      return request(`/planned-expenses?${q}`);
    },
    upcoming: (days = 60) => request(`/planned-expenses/upcoming?days=${days}`),
    markPaid: (data) => request('/planned-expenses/mark-paid', { method: 'POST', body: JSON.stringify(data) }),
    markUnpaid: (data) => request('/planned-expenses/mark-unpaid', { method: 'POST', body: JSON.stringify(data) }),
    get: (id) => request(`/planned-expenses/${id}`),
    create: (data) => request('/planned-expenses', { method: 'POST', body: JSON.stringify(data) }),
    update: (id, data) => request(`/planned-expenses/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
    delete: (id) => request(`/planned-expenses/${id}`, { method: 'DELETE' }),
  },

  payments: {
    list: (year) => request(`/payments?year=${year}`),
    update: (id, data) => request(`/payments/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
    rates: () => request('/payments/rates'),
    createRates: (data) => request('/payments/rates', { method: 'POST', body: JSON.stringify(data) }),
  },

  obligations: {
    types: () => request('/obligations/types'),
    calendar: (year, paymentType) => {
      let url = `/obligations/calendar?year=${year}`;
      if (paymentType) url += `&payment_type=${paymentType}`;
      return request(url);
    },
    decisions: (year) => request(`/obligations/decisions${year ? `?year=${year}` : ''}`),
    getDecision: (id) => request(`/obligations/decisions/${id}`),
    createDecision: (data) => request('/obligations/decisions', { method: 'POST', body: JSON.stringify(data) }),
    updateDecision: (id, data) => request(`/obligations/decisions/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
    applyPreset2026: () => request('/obligations/decisions/apply-preset-2026', { method: 'POST' }),
    generate: (year) => request(`/obligations/generate?year=${year}`, { method: 'POST' }),
    markPaid: (id, data) => request(`/obligations/obligations/${id}/mark-paid`, { method: 'PATCH', body: JSON.stringify(data) }),
    markUnpaid: (id) => request(`/obligations/obligations/${id}/mark-unpaid`, { method: 'PATCH' }),
    ipsQr: (id) => request(`/obligations/obligations/${id}/ips-qr`),
    summary: (year) => request(`/obligations/summary${year ? `?year=${year}` : ''}`),
  },

  dashboard: () => request('/dashboard'),
  bankImport: {
    parse: async (file) => {
      const formData = new FormData();
      formData.append('file', file);
      const t = getToken();
      const headers = t ? { Authorization: `Bearer ${t}` } : {};
      const res = await fetch(API_BASE + '/bank-import/parse', {
        method: 'POST',
        body: formData,
        headers,
      });
      if (res.status === 401) {
        setToken(null);
        setUser(null);
        window.location.href = '/login';
        throw new Error('Unauthorized');
      }
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || `HTTP ${res.status}`);
      }
      return res.json();
    },
    apply: (data) => request('/bank-import/apply', { method: 'POST', body: JSON.stringify(data) }),
  },
  enterprise: {
    get: () => request('/enterprise'),
    update: (data) => request('/enterprise', { method: 'PUT', body: JSON.stringify(data) }),
  },

  reports: {
    kpoCsvUrl: (year, month) => {
      let url = `${API_BASE}/reports/kpo/csv?year=${year}`;
      if (month) url += `&month=${month}`;
      return url;
    },
    kpoPdfUrl: (year, month) => {
      let url = `${API_BASE}/reports/kpo/pdf?year=${year}`;
      if (month) url += `&month=${month}`;
      return url;
    },
    async downloadPdf(year, month) {
      const url = this.kpoPdfUrl(year, month);
      const res = await fetch(url, {
        headers: { Authorization: `Bearer ${getToken()}` },
      });
      if (!res.ok) throw new Error('Ошибка загрузки');
      const blob = await res.blob();
      const u = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = u;
      a.download = `kpo_${year}${month ? `_${month}` : ''}.pdf`;
      a.click();
      URL.revokeObjectURL(u);
    },
    async downloadCsv(year, month) {
      const url = this.kpoCsvUrl(year, month);
      const res = await fetch(url, {
        headers: { Authorization: `Bearer ${getToken()}` },
      });
      if (!res.ok) throw new Error('Ошибка загрузки');
      const blob = await res.blob();
      const u = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = u;
      a.download = `kpo_${year}${month ? `_${month}` : ''}.csv`;
      a.click();
      URL.revokeObjectURL(u);
    },
  },
};
