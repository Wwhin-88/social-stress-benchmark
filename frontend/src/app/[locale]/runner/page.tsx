import { setRequestLocale } from 'next-intl/server'
import { RunnerClient } from '@/components/runner/RunnerClient'

export default async function RunnerPage({
  params,
}: {
  params: Promise<{ locale: string }>
}) {
  const { locale } = await params
  setRequestLocale(locale)

  return (
    <div className="max-w-7xl mx-auto px-6 py-8">
      <RunnerClient />
    </div>
  )
}
