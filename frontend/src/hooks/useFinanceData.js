import { useEffect, useState } from 'react'

export default function useFinanceData(active, key, load) {
  const [attempt, setAttempt] = useState(0)
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(true)
  const requestKey = `${key}/${attempt}`
  useEffect(() => {
    if (!active) return
    let current = true
    setLoading(true)
    load()
      .then((data) => {
        if (current) setResult({ key: requestKey, data })
      })
      .catch((error) => {
        if (current) setResult({ key: requestKey, error: error.message })
      })
      .finally(() => {
        if (current) setLoading(false)
      })
    return () => {
      current = false
    }
  }, [active, requestKey, load])
  return {
    data: result?.key === requestKey ? result.data : null,
    error: result?.key === requestKey ? result.error : null,
    pending: loading || result?.key !== requestKey,
    reload: () => setAttempt((value) => value + 1),
  }
}
