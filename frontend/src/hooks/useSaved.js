import { useCallback, useEffect, useState } from 'react'

const KEY = 'mk.saved'

/**
 * Saved places, kept in localStorage on this device.
 *
 * Only what the user explicitly saves is stored: a label and coordinates. A
 * device location obtained through the browser is used for the current lookup
 * and is never written here unless the user presses save.
 */
export function useSaved() {
  const [items, setItems] = useState(() => {
    try {
      const raw = JSON.parse(localStorage.getItem(KEY) || '[]')
      return Array.isArray(raw) ? raw : []
    } catch {
      return []
    }
  })

  useEffect(() => {
    try {
      localStorage.setItem(KEY, JSON.stringify(items))
    } catch {
      /* storage may be full or blocked; saving is a convenience, not a requirement */
    }
  }, [items])

  const save = useCallback((place) => {
    if (!place || !place.name) return
    setItems((prev) => {
      const key = (p) => `${p.name}|${Number(p.latitude).toFixed(3)}`
      const without = prev.filter((p) => key(p) !== key(place))
      return [
        {
          name: place.name,
          latitude: place.latitude,
          longitude: place.longitude,
          timezone: place.timezone || null,
          ward_id: place.ward_id || null,
        },
        ...without,
      ].slice(0, 8)
    })
  }, [])

  const remove = useCallback((name) => {
    setItems((prev) => prev.filter((p) => p.name !== name))
  }, [])

  const has = useCallback(
    (place) => place && items.some((p) => p.name === place.name),
    [items],
  )

  return { items, save, remove, has }
}
