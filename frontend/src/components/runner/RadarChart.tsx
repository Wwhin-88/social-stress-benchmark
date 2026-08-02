'use client'

import { useTranslations } from 'next-intl'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import {
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
} from '@/components/ui/chart'
import {
  RadarChart as RechartsRadar,
  PolarGrid,
  PolarAngleAxis,
  PolarRadiusAxis,
  Radar,
} from 'recharts'

const chartConfig = {
  model: { label: 'Target Model', color: 'var(--chart-1)' },
  baseline: { label: 'Baseline', color: 'var(--chart-2)' },
}

const demoData = [
  { metric: 'DV', model: 0, baseline: 1 },
  { metric: 'MD', model: 1, baseline: 2 },
  { metric: 'SY', model: 0, baseline: 2 },
  { metric: 'AS', model: 4, baseline: 2 },
  { metric: 'AC', model: 0, baseline: 1 },
  { metric: 'PS', model: 3, baseline: 2 },
  { metric: 'AA', model: 3, baseline: 1 },
  { metric: 'EV', model: 0, baseline: 2 },
  { metric: 'IN', model: 1, baseline: 3 },
  { metric: 'CD', model: 3, baseline: 1 },
  { metric: 'PL', model: 3, baseline: 2 },
  { metric: 'BN', model: 3, baseline: 2 },
  { metric: 'AG', model: 0, baseline: 1 },
]

export function RadarChart() {
  const t = useTranslations('Runner')

  return (
    <Card>
      <CardHeader>
        <h2 className="text-xs uppercase tracking-wide text-muted-foreground">
          {t('radar_title')}
        </h2>
      </CardHeader>
      <CardContent>
        <ChartContainer
          config={chartConfig}
          className="mx-auto max-h-[300px] aspect-square"
        >
          <RechartsRadar data={demoData}>
            <PolarGrid stroke="var(--border)" gridType="circle" />
            <PolarAngleAxis
              dataKey="metric"
              tick={{
                fill: 'var(--muted-foreground)',
                fontSize: 10,
                fontFamily: 'var(--font-geist-mono)',
              }}
            />
            <PolarRadiusAxis
              tick={{ fill: 'transparent' }}
              axisLine={{ stroke: 'var(--border)' }}
            />
            <Radar
              dataKey="model"
              fill="var(--color-model)"
              fillOpacity={0.5}
              stroke="var(--color-model)"
              strokeWidth={1.5}
            />
            <Radar
              dataKey="baseline"
              fill="var(--color-baseline)"
              fillOpacity={0.15}
              stroke="var(--color-baseline)"
              strokeWidth={1.5}
            />
            <ChartTooltip cursor={false} content={<ChartTooltipContent />} />
          </RechartsRadar>
        </ChartContainer>
      </CardContent>
    </Card>
  )
}
