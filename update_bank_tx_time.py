import os
import re

path = r"d:\Work\Programming\Buh_Prosp\frontend\src\pages\BankTransactions.jsx"
with open(path, "r", encoding="utf-8") as f:
    text = f.read()

# REMOVE PAGINATION STATE AND ADD YEAR/MONTH STATE
state_old = """    const [directionFilter, setDirectionFilter] = useState('all')
    const [page, setPage] = useState(0)"""
state_new = """    const [directionFilter, setDirectionFilter] = useState('all')
    const [year, setYear] = useState(new Date().getFullYear())
    const [month, setMonth] = useState('')"""
text = text.replace(state_old, state_new)

# REMOVE PAGINATION IN LOAD DATA AND USE YEAR/MONTH
load_old = """    const LIMIT = 50

    const loadData = async () => {
        setLoading(true)
        try {
            const params = { skip: page * LIMIT, limit: LIMIT }
            if (statusFilter !== 'all') params.status = statusFilter
            if (directionFilter !== 'all') params.direction = directionFilter"""
load_new = """    const loadData = async () => {
        setLoading(true)
        try {
            const params = { year }
            if (month) params.month = month
            if (statusFilter !== 'all') params.status = statusFilter
            if (directionFilter !== 'all') params.direction = directionFilter"""
text = text.replace(load_old, load_new)

# UPDATE DEPENDENCIES
deps_old = """    useEffect(() => {
        loadData()
    }, [statusFilter, directionFilter, page])"""
deps_new = """    useEffect(() => {
        loadData()
    }, [statusFilter, directionFilter, year, month])"""
text = text.replace(deps_old, deps_new)


# ADD YEAR/MONTH SELECTORS TO PAGE HEADER
header_old = """                <h1 className="page-title">{tr('bankTxTitle')}</h1>
                <div className="page-actions">
                    <select"""
header_new = """                <h1 className="page-title">{tr('bankTxTitle')}</h1>
                <div className="page-actions">
                    <select
                        value={year}
                        onChange={(e) => setYear(parseInt(e.target.value))}
                        className="input"
                    >
                        {[0, 1, 2].map((offset) => (
                            <option key={offset} value={new Date().getFullYear() - offset}>
                                {new Date().getFullYear() - offset}
                            </option>
                        ))}
                    </select>
                    <select
                        value={month}
                        onChange={(e) => setMonth(e.target.value)}
                        className="input"
                    >
                        <option value="">{tr('allMonths')}</option>
                        {[1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12].map((m) => (
                            <option key={m} value={m}>
                                {new Date(2000, m - 1).toLocaleString('ru-RU', { month: 'long' })}
                            </option>
                        ))}
                    </select>
                    <select"""
text = text.replace(header_old, header_new)

# REMOVE SET PAGE FROM STATUS FILTER
status_old = """onChange={e => { setStatusFilter(e.target.value); setPage(0) }}"""
status_new = """onChange={e => setStatusFilter(e.target.value)}"""
text = text.replace(status_old, status_new)

# REMOVE SET PAGE FROM DIRECTION FILTER
direction_old = """onChange={e => { setDirectionFilter(e.target.value); setPage(0) }}"""
direction_new = """onChange={e => setDirectionFilter(e.target.value)}"""
text = text.replace(direction_old, direction_new)

# REMOVE BOTTOM PAGINATION CONTROLS
pagination_old = """                    </table>
                </div>
                <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', gap: '1rem', marginTop: '1rem' }}>
                    <button
                        className="btn btn-secondary"
                        disabled={page === 0}
                        onClick={() => setPage(page - 1)}
                    >
                        ← {tr('prev')}
                    </button>
                    <span>{tr('page')} {page + 1}</span>
                    <button
                        className="btn btn-secondary"
                        disabled={data.length < LIMIT}
                        onClick={() => setPage(page + 1)}
                    >
                        {tr('next')} →
                    </button>
                </div>
            </main>"""
pagination_new = """                    </table>
                </div>
            </main>"""
text = text.replace(pagination_old, pagination_new)

with open(path, "w", encoding="utf-8") as f:
    f.write(text)
print("Updated BankTransactions.jsx with year/month filters")
