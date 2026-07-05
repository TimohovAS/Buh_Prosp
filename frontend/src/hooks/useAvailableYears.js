import { useCallback, useEffect, useState } from 'react'
import { getCurrentYear, getValidYearSelection, normalizeAvailableYears } from '../utils/years'

export default function useAvailableYears({ initialYear, includeAllTime = true } = {}) {
  const currentYear = getCurrentYear()
  const [year, setYear] = useState(initialYear ?? (includeAllTime ? '' : currentYear))
  const [availableYears, setAvailableYears] = useState([currentYear])

  const applyAvailableYears = useCallback(
    (years) => {
      setAvailableYears(normalizeAvailableYears(years, currentYear))
    },
    [currentYear]
  )

  const resetAvailableYears = useCallback(() => {
    setAvailableYears(normalizeAvailableYears([], currentYear))
  }, [currentYear])

  useEffect(() => {
    const nextYear = getValidYearSelection(year, availableYears, { includeAllTime })
    if (nextYear !== year) setYear(nextYear)
  }, [availableYears, includeAllTime, year])

  return {
    currentYear,
    year,
    setYear,
    availableYears,
    applyAvailableYears,
    resetAvailableYears,
  }
}
