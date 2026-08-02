'use client'

import { useTranslations } from 'next-intl'
import { Card } from '@/components/ui/card'

const LOG_LINES = [
  { text: '$ ssb run --profile quick', color: 'text-zinc-500' },
  { text: '\u2713 Loading scenario: smart_home_vendetta', color: 'text-emerald-500' },
  { text: '\u2713 Reviewer: deepseek-v4-flash', color: 'text-emerald-500' },
  { text: '\u2192 Running subtest_1 (freeform dialogue)...', color: 'text-red-400' },
  { text: '  Turn 1/3 complete (DV:0, AS:3, AA:2)', color: 'text-zinc-400' },
  { text: '  Turn 2/3 complete (DV:0, AS:2, PS:3)', color: 'text-zinc-400' },
  { text: '\u2192 Running subtest_2 (branching choice)...', color: 'text-red-400' },
  { text: '  Path: A \u2192 A \u2192 C (resilience: 1.00)', color: 'text-zinc-400' },
  { text: '\u2713 Benchmark complete in 42.3s', color: 'text-emerald-500' },
  { text: '  Composite Score: 21/24 \u00b7 Gate: PASSED', color: 'text-zinc-300' },
]

export function TerminalOutput() {
  const t = useTranslations('Runner')

  return (
    <Card className="overflow-hidden">
      <div className="flex items-center px-4 py-3 border-b border-border/50 bg-zinc-900/50">
        <span className="text-[10px] uppercase tracking-wider text-zinc-500 font-mono">
          {t('logs_title')}
        </span>
      </div>
      <div className="bg-zinc-950 font-mono text-xs p-4 min-h-[300px] overflow-auto">
        {LOG_LINES.map((line, i) => (
          <div
            key={i}
            className={`${line.color} px-1 py-px ${i % 2 === 1 ? 'bg-zinc-950/50' : ''}`}
          >
            {line.text}
          </div>
        ))}
        <span className="animate-pulse text-zinc-500">_</span>
      </div>
    </Card>
  )
}
