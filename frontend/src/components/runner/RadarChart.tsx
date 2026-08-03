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

export interface RadarRow {
  metric: string
  model: number
  baseline: number
}

interface RadarChartProps {
  data: RadarRow[] | null
}

const chartConfig = {
  model: { label: 'Target Model', color: 'var(--chart-1)' },
  baseline: { label: 'Baseline', color: 'var(--chart-2)' },
}

export function RadarChart({ data }: RadarChartProps) {
  const t = useTranslations('Runner')

  return (
    <Card>
      <CardHeader>
        <h2 className="text-xs uppercase tracking-wide text-muted-foreground">
          {t('radar_title')}
        </h2>
      </CardHeader>
      <CardContent>
        {data === null ? (
          <div className="flex items-center justify-center min-h-[300px] text-sm text-muted-foreground">
            {t('no_data')}
          </div>
        ) : (
          <ChartContainer
            config={chartConfig}
            className="mx-auto max-h-[300px] aspect-square"
          >
            <RechartsRadar data={data}>
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
        )}
      </CardContent>
    </Card>
  )
}
