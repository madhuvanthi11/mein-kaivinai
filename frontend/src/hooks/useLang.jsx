import { createContext, useContext, useEffect, useMemo, useState } from 'react'
import { makeT, LANGS } from '../i18n'

const Ctx = createContext(null)
const KEY = 'mk.lang'

function initial() {
  const saved = localStorage.getItem(KEY)
  if (saved && LANGS.some((l) => l.code === saved)) return saved
  const nav = (navigator.language || 'en').slice(0, 2)
  return LANGS.some((l) => l.code === nav) ? nav : 'en'
}

export function LangProvider({ children }) {
  const [lang, setLangState] = useState(initial)

  useEffect(() => {
    document.documentElement.lang = lang
  }, [lang])

  const value = useMemo(
    () => ({
      lang,
      setLang: (l) => {
        localStorage.setItem(KEY, l)
        setLangState(l)
      },
      t: makeT(lang),
    }),
    [lang],
  )

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}

export function useLang() {
  const v = useContext(Ctx)
  if (!v) throw new Error('useLang must be used inside LangProvider')
  return v
}
