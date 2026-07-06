globalThis.localStorage = {
  getItem: () => null,
  setItem: () => {},
}

const {
  getMonthNamesFull,
  getMonthNamesShort,
  setLang,
  translations: dictionaries,
} = await import('../src/i18n.js')

function sortedKeys(dictionary) {
  return Object.keys(dictionary).sort((a, b) => a.localeCompare(b))
}

const [baseLang, baseDictionary] = Object.entries(dictionaries)[0]
const baseKeys = sortedKeys(baseDictionary)
const baseSet = new Set(baseKeys)
const failures = []

for (const [lang, dictionary] of Object.entries(dictionaries)) {
  const keys = sortedKeys(dictionary)
  const keySet = new Set(keys)
  const missing = baseKeys.filter((key) => !keySet.has(key))
  const extra = keys.filter((key) => !baseSet.has(key))

  if (missing.length || extra.length) {
    failures.push({ lang, missing, extra })
  }
}

if (failures.length) {
  console.error(`i18n key mismatch against '${baseLang}'`)
  for (const failure of failures) {
    if (failure.missing.length) {
      console.error(`\n${failure.lang} missing keys:`)
      for (const key of failure.missing) console.error(`  - ${key}`)
    }
    if (failure.extra.length) {
      console.error(`\n${failure.lang} extra keys:`)
      for (const key of failure.extra) console.error(`  - ${key}`)
    }
  }
  process.exit(1)
}

console.log(`i18n keys match: ${Object.keys(dictionaries).join(', ')} (${baseKeys.length} keys)`)

const expectedMonthNames = {
  ru: {
    short: ['Янв', 'Фев', 'Мар', 'Апр', 'Май', 'Июн', 'Июл', 'Авг', 'Сен', 'Окт', 'Ноя', 'Дек'],
    full: [
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
    ],
  },
  sr: {
    short: ['Јан', 'Феб', 'Мар', 'Апр', 'Мај', 'Јун', 'Јул', 'Авг', 'Сеп', 'Окт', 'Нов', 'Дец'],
    full: [
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
    ],
  },
}

for (const [lang, expected] of Object.entries(expectedMonthNames)) {
  setLang(lang)
  const actualShort = getMonthNamesShort()
  const actualFull = getMonthNamesFull()
  if (JSON.stringify(actualShort) !== JSON.stringify(expected.short)) {
    console.error(`i18n month short names mismatch for '${lang}'`)
    process.exit(1)
  }
  if (JSON.stringify(actualFull) !== JSON.stringify(expected.full)) {
    console.error(`i18n month full names mismatch for '${lang}'`)
    process.exit(1)
  }
}

console.log('i18n month names match')
