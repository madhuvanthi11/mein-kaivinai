import { CircleMarker, MapContainer, Popup, TileLayer, Tooltip, useMap } from 'react-leaflet'
import 'leaflet/dist/leaflet.css'
import { useEffect } from 'react'
import { HEX, num } from '../lib/fmt'
import { useLang } from '../hooks/useLang'

function Recenter({ center, zoom }) {
  const map = useMap()
  useEffect(() => {
    if (center) map.setView(center, zoom ?? map.getZoom(), { animate: true })
  }, [center && center[0], center && center[1], zoom])
  return null
}

/**
 * Ward risk points on OpenStreetMap tiles. No Google Maps dependency.
 * Every circle is a ward whose weather was fetched individually from Open-Meteo.
 */
export default function RiskMap({ center, zoom = 12, points = [], selectedId, onSelect }) {
  const { t } = useLang()

  return (
    <div>
      <MapContainer center={center} zoom={zoom} className="map" scrollWheelZoom>
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          url="https://tile.openstreetmap.org/{z}/{x}/{y}.png"
          maxZoom={19}
        />
        <Recenter center={center} zoom={zoom} />

        {points.map((p) => {
          const ward = p.ward
          const level = p.risk.level
          const isSelected = ward.id === selectedId
          return (
            <CircleMarker
              key={ward.id}
              center={[ward.latitude, ward.longitude]}
              radius={isSelected ? 14 : 10}
              eventHandlers={onSelect ? { click: () => onSelect(ward.id) } : undefined}
              pathOptions={{
                color: isSelected ? '#16180f' : '#ffffff',
                weight: isSelected ? 3 : 2,
                fillColor: HEX[level] || '#9aa091',
                fillOpacity: 0.92,
              }}
            >
              <Tooltip direction="top" offset={[0, -6]}>
                <strong>{ward.name}</strong> — {t(level)} {p.risk.score}
              </Tooltip>
              <Popup>
                <strong>{ward.name}</strong>
                <br />
                {ward.city}
                <br />
                {t('impactTitle')}: {t(level)} · {p.risk.score}
                {t('outOf')}
                <br />
                {t('temperature')}: {num(p.current.temperature_c, 1)}°C
                {p.thermal && (
                  <>
                    <br />
                    UTCI {num(p.thermal.utci.value, 1)}° · WBGT* {num(p.thermal.wbgt.value, 1)}° · {t('heatIndexShort')}{' '}
                    {num(p.thermal.heat_index.value, 1)}°
                    <br />
                    {t('htsName')}: {num(p.thermal.human_thermal_stress.score)}
                    {t('outOf')}
                    {p.thermal.window_24h && p.thermal.window_24h.persistence && (
                      <>
                        <br />
                        {t('persistenceLabel')}: {p.thermal.window_24h.persistence.longest_high_stress_run_h} h
                      </>
                    )}
                    {p.forecast_brief && (
                      <>
                        <br />
                        {p.forecast_brief.map((d) => `${d.date.slice(8)}:${d.level ? t(d.level).slice(0, 3) : '—'}`).join(' · ')}
                      </>
                    )}
                    {p.actions && p.actions[0] && (
                      <>
                        <br />
                        <em>{t(`act_${p.actions[0].code}`)}</em>
                      </>
                    )}
                  </>
                )}
              </Popup>
            </CircleMarker>
          )
        })}
      </MapContainer>
      <p className="muted" style={{ marginTop: 8, fontSize: 13 }}>
        {t('mapNote')}
      </p>
    </div>
  )
}
