import en from './en'
import ta from './ta'

/**
 * Adding a language
 * -----------------
 * 1. Copy en.js to the new code, e.g. hi.js, and translate the values.
 * 2. Import it here and add one line to BUNDLES and LANGS.
 *
 * Nothing else in the app needs to change: components only ever call t(key),
 * and any key a bundle has not translated yet falls back to English rather than
 * showing a blank or a raw key. Partial bundles are therefore safe to ship.
 *
 * Planned: hi (हिन्दी), te (తెలుగు), kn (ಕನ್ನಡ), ml (മലയാളം). These are
 * intentionally absent until a fluent speaker writes them -- a machine-translated
 * safety instruction is worse than no translation at all.
 */
export const BUNDLES = { en, ta }

export const LANGS = [
  { code: 'en', label: 'English' },
  { code: 'ta', label: 'தமிழ்' },
]

const ALIASES = {
  temperature: 'temperatureDriver',
  humidity: 'humidityDriver',
}

export function makeT(lang) {
  const bundle = BUNDLES[lang] || en
  return function t(key, context) {
    if (key == null) return ''
    const k = context === 'driver' && ALIASES[key] ? ALIASES[key] : key
    const v = bundle[k]
    if (v !== undefined) return v
    const fallback = en[k]
    if (fallback !== undefined) return fallback
    return key
  }
}
