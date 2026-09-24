// Сколько отправить в cash_paid_amount. Пустое поле и нетронутый остаток,
// подставленный формой, уходят как null: сервер сам посчитает остаток по тем
// дате, работнику и периоду, что уходят сейчас. Иначе число, оставшееся от
// прежних дат, ушло бы как введённое явно, и сервер его уже не пересчитал бы.
export const payoutCashForSubmit = (fieldValue, autoFilledValue) => {
  const value = String(fieldValue ?? '').trim()
  if (value === '' || (autoFilledValue && value === String(autoFilledValue))) return null
  const amount = Number(value)
  return Number.isFinite(amount) ? amount : null
}
