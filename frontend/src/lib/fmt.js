/** Formatting helpers. None of these invent a value: a missing number prints
 *  an em dash rather than a zero. */

export const LEVELS = ['Low', 'Moderate', 'High', 'Very High', 'Extreme']

export const COLORS = {
  Low: 'var(--low)',
  Moderate: 'var(--moderate)',
  High: 'var(--high)',
  'Very High': 'var(--veryhigh)',
  Extreme: 'var(--extreme)',
}

/** Solid hex values, for Leaflet and anywhere CSS variables cannot reach. */
export const HEX = {
  Low: '#1f7a4c',
  Moderate: '#b58200',
  High: '#d95a09',
  'Very High': '#c1102b',
  Extreme: '#6b0f2a',
}

export const DASH = '—'

export function num(v, digits = 0) {
  if (v === null || v === undefined || Number.isNaN(Number(v))) return DASH
  return Number(v).toFixed(digits)
}

export function signed(v, digits = 1) {
  if (v === null || v === undefined || Number.isNaN(Number(v))) return DASH
  const n = Number(v)
  return `${n > 0 ? '+' : ''}${n.toFixed(digits)}`
}

/** Open-Meteo returns local wall-clock strings like 2026-09-21T14:00.
 *  They are parsed as-is; no timezone maths is applied so the time shown is
 *  the time at the location. */
export function hourLabel(iso) {
  if (!iso) return DASH
  const h = Number(iso.slice(11, 13))
  const m = iso.slice(14, 16)
  const suffix = h < 12 ? 'AM' : 'PM'
  const h12 = h % 12 === 0 ? 12 : h % 12
  return `${h12}:${m} ${suffix}`
}

export function shortHour(iso) {
  if (!iso) return DASH
  const h = Number(iso.slice(11, 13))
  const suffix = h < 12 ? 'am' : 'pm'
  const h12 = h % 12 === 0 ? 12 : h % 12
  return `${h12}${suffix}`
}

export function dayHour(iso) {
  if (!iso) return DASH
  return `${iso.slice(8, 10)} ${shortHour(iso)}`
}

export function stamp(iso) {
  if (!iso) return DASH
  return `${iso.slice(8, 10)}/${iso.slice(5, 7)} ${hourLabel(iso)}`
}

export function sameHour(a, b) {
  return Boolean(a && b && a.slice(0, 13) === b.slice(0, 13))
}

/** Peak end is exclusive, so an hour is inside the window when start <= t < end. */
export function inWindow(iso, start, end) {
  if (!iso || !start || !end) return false
  return iso >= start && iso < end
}

/** Replace {name} placeholders. Missing params are left visible rather than guessed. */
export function fill(str, params = {}) {
  return String(str).replace(/\{(\w+)\}/g, (m, k) => (params[k] !== undefined && params[k] !== null ? params[k] : m))
}

/** 'YYYY-MM-DD' -> short weekday + day/month, parsed without timezone shifts. */
export function dayLabel(iso, locale = 'en') {
  if (!iso) return DASH
  const [y, m, d] = iso.slice(0, 10).split('-').map(Number)
  const dt = new Date(Date.UTC(y, m - 1, d))
  return `${new Intl.DateTimeFormat(locale === 'ta' ? 'ta-IN' : 'en-IN', { weekday: 'short', timeZone: 'UTC' }).format(dt)} ${String(d).padStart(2, '0')}/${String(m).padStart(2, '0')}`
}

export const hm = (iso) => (iso ? iso.slice(11, 16) : DASH)
