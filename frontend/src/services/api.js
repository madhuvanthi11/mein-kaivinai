/** Thin client over the FastAPI backend.
 *
 *  The browser never calls Open-Meteo directly -- every weather request goes
 *  through the backend so caching, normalization and error handling happen in
 *  one place.
 */

export class ApiError extends Error {
  constructor(kind, detail) {
    super(detail || kind)
      // 'unavailable' | 'notfound' | 'bad' | 'unauthenticated' | 'forbidden' | 'conflict'
    this.kind = kind
    this.detail = detail
  }
}

/** Credential supplier, installed once by the auth provider.
 *  Returns the headers that identify the caller, or {} when signed out. */
let authHeaders = async () => ({})

export function setAuthHeaderSource(fn) {
  authHeaders = fn
}

async function request(path, options) {
  let res
  try {
    const extra = await authHeaders()
    res = await fetch(path, {
      ...options,
      headers: {
        ...(options && options.body ? { 'Content-Type': 'application/json' } : {}),
        ...extra,
        ...((options && options.headers) || {}),
      },
    })
  } catch {
    throw new ApiError('unavailable', 'Network request failed')
  }

  let body = null
  try {
    body = await res.json()
  } catch {
    body = null
  }

  if (res.ok) return body

  const detail = body && body.detail ? body.detail : null
  if (res.status === 401) throw new ApiError('unauthenticated', detail)
  if (res.status === 403) throw new ApiError('forbidden', detail)
  if (res.status === 409) throw new ApiError('conflict', detail)
  if (res.status === 404) throw new ApiError('notfound', detail)
  if (res.status === 503) throw new ApiError('unavailable', detail)
  throw new ApiError('bad', detail || `Request failed (${res.status})`)
}

const q = (params) =>
  Object.entries(params)
    .filter(([, v]) => v !== undefined && v !== null && v !== '')
    .map(([k, v]) => `${k}=${encodeURIComponent(v)}`)
    .join('&')

export const geocode = (query) => request(`/api/geocode?${q({ query })}`)

export const summary = (loc) =>
  request(`/api/weather/summary?${q({ lat: loc.latitude, lon: loc.longitude, name: loc.name })}`)

export const wardView = (wardId) => request(`/api/wards/${encodeURIComponent(wardId)}`)

export const wardRegistry = () => request('/api/wards')

export const nearestWard = (lat, lon) => request(`/api/wards/nearest?${q({ lat, lon })}`)

export const monitorCity = (city, threshold) =>
  request(`/api/monitor/city?${q({ city, threshold })}`)

export const alertForWard = (wardId, threshold) =>
  request(`/api/alerts/ward/${encodeURIComponent(wardId)}?${q({ threshold })}`, { method: 'POST' })

export const status = () => request('/api/status')

const post = (path, body) =>
  request(path, { method: 'POST', body: JSON.stringify(body || {}) })

// ---------------------------------------------------------------- identity
export const me = () => request('/api/me')

// ---------------------------------------------------------------- admin
export const adminProposals = (city, threshold, detect = true) =>
  request(`/api/admin/proposals?${q({ city, threshold, detect })}`)

export const submitProposal = (id, body) => post(`/api/admin/proposals/${id}/submit`, body)

export const rejectProposal = (id, reason) =>
  post(`/api/admin/proposals/${id}/reject`, { reason })

// ---------------------------------------------------------------- government
export const govQueue = () => request('/api/gov/queue')

export const govApprove = (id, reason) => post(`/api/gov/alerts/${id}/approve`, { reason })

export const govModify = (id, body) => post(`/api/gov/alerts/${id}/modify`, body)

export const govReject = (id, reason) => post(`/api/gov/alerts/${id}/reject`, { reason })

export const govIssue = (id) => post(`/api/gov/alerts/${id}/issue`, {})

export const govExpire = (id) => post(`/api/gov/alerts/${id}/expire`, {})

export const govAdvisory = (body) => post('/api/gov/advisories', body)

export const templates = () => request('/api/templates')

// ---------------------------------------------------------------- citizen
export const wardFeed = (wardId) => request(`/api/alerts/feed/${encodeURIComponent(wardId)}`)

export const inbox = () => request('/api/notifications')

export const markRead = (id) => post(`/api/notifications/${id}/read`, {})

export const mySubscription = () => request('/api/subscriptions/me')

export const subscribe = (wardIds) =>
  post('/api/subscriptions', { ward_ids: wardIds, consent: true })

export const unsubscribe = () => request('/api/subscriptions', { method: 'DELETE' })

/** Coordinates -> place name (OpenStreetMap Nominatim, via the backend).
 *  Separate from the weather call so a naming failure never blocks the reading. */
export const reverseGeocode = (lat, lon) => request(`/api/reverse-geocode?${q({ lat, lon })}`)
