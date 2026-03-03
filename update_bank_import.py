import os
import re

path = r"d:\Work\Programming\Buh_Prosp\frontend\src\pages\BankImport.jsx"
with open(path, "r", encoding="utf-8") as f:
    text = f.read()

# Replace state
text = text.replace("const [file, setFile] = useState(null)", "const [files, setFiles] = useState([])")
text = text.replace("const [parseMeta, setParseMeta] = useState(null)", "const [parseMeta, setParseMeta] = useState([])\n  const [skippedFiles, setSkippedFiles] = useState([])")

# Replace handleFileChange
old_handle = """  const handleFileChange = async (e) => {
    const f = e.target.files?.[0] || null
    setFile(f)
    setTransactions([])
    setSelections({})
    setParseMeta(null)
    setResult(null)
    if (!f) return
    setLoading(true)
    try {
      const parsed = await api.bankImport.parse(f)
      const tx = parsed.transactions || []
      setTransactions(tx)
      const sel = {}
      tx.forEach((t, i) => { sel[i] = { selected: true, type: t.type } })
      setSelections(sel)
      setParseMeta({
        file_name: parsed.file_name || f.name,
        file_hash: parsed.file_hash,
        already_imported: !!parsed.already_imported,
        imported_file: parsed.imported_file || null,
      })
      if (Array.isArray(parsed.recent_files)) setRecentFiles(parsed.recent_files)
      if (parsed.already_imported) {
        alert(tr('bankImportAlreadyImported'))
      }
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }"""

new_handle = """  const handleFileChange = async (e) => {
    const selectedFiles = e.target.files || []
    if (selectedFiles.length === 0) return
    setFiles(Array.from(selectedFiles))
    setTransactions([])
    setSelections({})
    setParseMeta([])
    setSkippedFiles([])
    setResult(null)
    setLoading(true)
    try {
      const parsed = await api.bankImport.parse(selectedFiles)
      const tx = parsed.transactions || []
      setTransactions(tx)
      const sel = {}
      tx.forEach((t, i) => { sel[i] = { selected: true, type: t.type } })
      setSelections(sel)
      setParseMeta(parsed.parsed_files || [])
      setSkippedFiles(parsed.skipped_files || [])
      if (Array.isArray(parsed.recent_files)) setRecentFiles(parsed.recent_files)
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }"""
text = text.replace(old_handle, new_handle)

# Replace handleApply
old_apply = """  const handleApply = async () => {
    const items = transactions
      .map((tx, i) => ({ tx, i, sel: selections[i] }))
      .filter(({ sel }) => sel?.selected)
    if (items.length === 0) return alert(tr('selectAtLeastOne'))
    if (parseMeta?.already_imported) return alert(tr('bankImportAlreadyImported'))
    setApplying(true)
    setResult(null)
    try {
      const body = {
        transactions: items.map(({ tx, i }) => ({
          type: selections[i].type,
          tx,
          client_id: selections[i].client_id || null,
          invoice_number: selections[i].invoice_number || null,
        })),
        file_hash: parseMeta?.file_hash || null,
        file_name: parseMeta?.file_name || file?.name || null,
        file_size: file?.size || null,
        transaction_count: transactions.length,
      }
      const res = await api.bankImport.apply(body)
      setResult(res)
      setTransactions([])
      setFile(null)
      setSelections({})
      setParseMeta(null)
      if (Array.isArray(res.recent_files)) setRecentFiles(res.recent_files)
      else api.bankImport.recentFiles(10).then((r) => setRecentFiles(r.items || [])).catch(() => { })
    } catch (e) {
      console.error(e)
    } finally {
      setApplying(false)
    }
  }"""

new_apply = """  const handleApply = async () => {
    const items = transactions
      .map((tx, i) => ({ tx, i, sel: selections[i] }))
      .filter(({ sel }) => sel?.selected)
    if (items.length === 0) { console.error(tr('selectAtLeastOne')); return; }
    setApplying(true)
    setResult(null)
    try {
      const body = {
        transactions: items.map(({ tx, i }) => ({
          type: selections[i].type,
          tx,
          file_hash: tx.file_hash || null,
          client_id: selections[i].client_id || null,
          invoice_number: selections[i].invoice_number || null,
        })),
        files: parseMeta || [],
      }
      const res = await api.bankImport.apply(body)
      setResult(res)
      setTransactions([])
      setFiles([])
      setSelections({})
      setParseMeta([])
      setSkippedFiles([])
      if (Array.isArray(res.recent_files)) setRecentFiles(res.recent_files)
      else api.bankImport.recentFiles(10).then((r) => setRecentFiles(r.items || [])).catch(() => { })
    } catch (e) {
      console.error(e)
    } finally {
      setApplying(false)
    }
  }"""
text = text.replace(old_apply, new_apply)

# Replace input tag
old_input = """<input
              type="file"
              accept=".xls,.xlsx"
              onChange={handleFileChange}
              disabled={loading}
            />"""
new_input = """<input
              type="file"
              multiple
              accept=".xls,.xlsx"
              onChange={handleFileChange}
              disabled={loading}
            />"""
text = text.replace(old_input, new_input)


# Replace already_imported display with skippedFiles display
old_imported = """{parseMeta?.already_imported && parseMeta.imported_file && (
            <div style={{ marginTop: '0.75rem', color: 'var(--color-warning)' }}>
              {tr('bankImportAlreadyImportedAt')
                .replace('{file}', parseMeta.imported_file.file_name || parseMeta.file_name || '-')
                .replace('{date}', parseMeta.imported_file.imported_at ? new Date(parseMeta.imported_file.imported_at).toLocaleString() : '-')}
            </div>
          )}"""
new_imported = """{skippedFiles && skippedFiles.length > 0 && (
            <div style={{ marginTop: '0.75rem', color: 'var(--color-warning)' }}>
              <strong>Пропущенные файлы ({skippedFiles.length}):</strong>
              <ul style={{ margin: '0.25rem 0 0 1.5rem', padding: 0 }}>
                {skippedFiles.map((sf, idx) => (
                  <li key={idx}>{sf.file_name} - {sf.reason}</li>
                ))}
              </ul>
            </div>
          )}"""
text = text.replace(old_imported, new_imported)


with open(path, "w", encoding="utf-8") as f:
    f.write(text)
print("Updated BankImport.jsx")
