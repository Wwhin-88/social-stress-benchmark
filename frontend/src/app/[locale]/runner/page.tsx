import { setRequestLocale } from 'next-intl/server'
import { ConfigPanel } from '@/components/runner/ConfigPanel'
import { TerminalOutput } from '@/components/runner/TerminalOutput'
import { RadarChart } from '@/components/runner/RadarChart'

export default async function RunnerPage({
  params,
}: {
  params: Promise<{ locale: string }>
}) {
  const { locale } = await params
  setRequestLocale(locale)

  return (
    <div className="max-w-7xl mx-auto px-6 py-8">
      <div className="flex gap-6 items-start">
        <div className="w-[360px] shrink-0">
          <ConfigPanel />
        </div>
        <div className="flex-1 min-w-0 space-y-6">
          <TerminalOutput />
          <RadarChart />
        </div>
      </div>
    </div>
  )
}
