import ru from './i18n/ru.js'
import sr from './i18n/sr.js'

export const translations = {
  ru,
  sr,
}

let lang = localStorage.getItem('prospel_lang') || 'sr'

export function setLang(l) {
  lang = translations[l] ? l : 'sr'
  localStorage.setItem('prospel_lang', lang)
}

export function getLang() {
  return lang
}

export function tr(key, replacements = null) {
  const value = translations[lang]?.[key] ?? translations.sr[key] ?? key
  if (!replacements) return value
  return Object.entries(replacements).reduce(
    (text, [name, replacement]) => text.replaceAll(`{${name}}`, String(replacement ?? '')),
    value
  )
}

const MONTH_NAMES_SR = ['Јан', 'Феб', 'Мар', 'Апр', 'Мај', 'Јун', 'Јул', 'Авг', 'Сеп', 'Окт', 'Нов', 'Дец']
const MONTH_NAMES_RU = ['Янв', 'Фев', 'Мар', 'Апр', 'Май', 'Июн', 'Июл', 'Авг', 'Сен', 'Окт', 'Ноя', 'Дек']
const MONTH_NAMES_FULL_SR = [
  'јануар',
  'фебруар',
  'март',
  'април',
  'мај',
  'јун',
  'јул',
  'август',
  'септембар',
  'октобар',
  'новембар',
  'децембар',
]
const MONTH_NAMES_FULL_RU = [
  'январь',
  'февраль',
  'март',
  'апрель',
  'май',
  'июнь',
  'июль',
  'август',
  'сентябрь',
  'октябрь',
  'ноябрь',
  'декабрь',
]

export function getMonthNamesShort() {
  return lang === 'ru' ? MONTH_NAMES_RU : MONTH_NAMES_SR
}

export function getMonthNamesFull() {
  return lang === 'ru' ? MONTH_NAMES_FULL_RU : MONTH_NAMES_FULL_SR
}
