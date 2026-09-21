import {
  Bar,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ReferenceArea,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { dayHour, hourLabel, num } from '../lib/fmt'
import { useLang } from '../hooks/useLang'

/** Temperature, feels-like and risk on one time axis, straight from the API. */
export default function HourlyChart({ hourly, peakStart, peakEnd }) {
  const { t } = useLang()

  const data = hourly.map((h) => ({
    time: h.time,
    label: dayHour(h.time),
    temp: h.temperature_c,
    feels: h.apparent_temperature_c,
    risk: h.risk_score,
  }))

  const from = peakStart && data.find((d) => d.time === peakStart)
  const to = peakEnd && [...data].reverse().find((d) => d.time < peakEnd)

  return (
    <ResponsiveContainer width="100%" height={300}>
      <ComposedChart data={data} margin={{ top: 6, right: 4, bottom: 0, left: -18 }}>
        <CartesianGrid stroke="#ccd0c5" vertical={false} />
        <XAxis
          dataKey="label"
          interval={7}
          tick={{ fontSize: 11, fill: '#4a4e42' }}
          tickLine={false}
          stroke="#9aa091"
        />
        <YAxis
          yAxisId="t"
          unit="°"
          tick={{ fontSize: 11, fill: '#4a4e42' }}
          tickLine={false}
          stroke="#9aa091"
        />
        <YAxis
          yAxisId="r"
          orientation="right"
          domain={[0, 100]}
          tick={{ fontSize: 11, fill: '#4a4e42' }}
          tickLine={false}
          stroke="#9aa091"
        />
        <Tooltip
          contentStyle={{
            border: '1px solid #16180f',
            borderRadius: 6,
            fontSize: 13,
            fontFamily: 'Archivo, system-ui, sans-serif',
          }}
          labelFormatter={(_, p) => (p && p[0] ? hourLabel(p[0].payload.time) : '')}
          formatter={(v, name) => [name === t('riskScore') ? num(v) : `${num(v, 1)}°C`, name]}
        />
        <Legend wrapperStyle={{ fontSize: 13, paddingTop: 6 }} />
        {from && to && (
          <ReferenceArea
            yAxisId="t"
            x1={from.label}
            x2={to.label}
            fill="#c1102b"
            fillOpacity={0.1}
            stroke="#c1102b"
            strokeOpacity={0.35}
          />
        )}
        <Bar yAxisId="r" dataKey="risk" name={t('riskScore')} fill="#9aa091" fillOpacity={0.45} />
        <Line
          yAxisId="t"
          dataKey="temp"
          name={t('temperature')}
          stroke="#16180f"
          dot={false}
          strokeWidth={2}
        />
        <Line
          yAxisId="t"
          dataKey="feels"
          name={t('feelsShort')}
          stroke="#c1102b"
          dot={false}
          strokeWidth={2}
        />
      </ComposedChart>
    </ResponsiveContainer>
  )
}
