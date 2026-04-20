import { useCallback } from 'react'
import { UI_DASH } from '../utils/formatters'

export default function useCategoryProjectResolver(categories, lang = 'ru') {
  const getCategoryById = useCallback((categoryId) => (
    categories.find((item) => String(item.id) === String(categoryId)) || null
  ), [categories])

  const getCategoryDefaultProjectId = useCallback((categoryId) => {
    const category = getCategoryById(categoryId)
    return category?.default_project_id ? String(category.default_project_id) : ''
  }, [getCategoryById])

  const usesCategoryProject = useCallback((categoryId) => Boolean(getCategoryDefaultProjectId(categoryId)), [getCategoryDefaultProjectId])

  const getCategoryLabel = useCallback((categoryOrId, emptyLabel = UI_DASH) => {
    const category = typeof categoryOrId === 'object' && categoryOrId !== null
      ? getCategoryById(categoryOrId.category_id ?? categoryOrId.id ?? '')
      : getCategoryById(categoryOrId)
    if (!category) return emptyLabel
    return lang === 'ru' ? category.name_ru : category.name_sr
  }, [getCategoryById, lang])

  return {
    getCategoryById,
    getCategoryDefaultProjectId,
    usesCategoryProject,
    getCategoryLabel,
  }
}
