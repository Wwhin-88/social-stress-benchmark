'use client'

import { useRef, useEffect } from 'react'
import { useTranslations } from 'next-intl'
import { Card } from '@/components/ui/card'

interface TerminalOutputProps {
  logs: Array<{ text: string; color: string }>
  isRunning: boolean
}

export function TerminalOutput({ logs, isRunning }: TerminalOutputProps) {
  const t = useTranslations('Runner')
  const scrollRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [logs])

  return (
    <Card className="overflow-hidden">
      <div className="flex items-center px-4 py-3 border-b border-border/50 bg-zinc-900/50">
        <span className="text-[10px] uppercase tracking-wider text-zinc-500 font-mono">
          {t('logs_title')}
        </span>
      </div>
      <div
        ref={scrollRef}
        className="bg-zinc-950 font-mono text-xs p-4 min-h-[300px] overflow-auto"
      >
        {logs.map((line, i) => (
          <div
            key={i}
            className={`${line.color} px-1 py-px ${i % 2 === 1 ? 'bg-zinc-950/50' : ''}`}
          >
            {line.text}
          </div>
        ))}
        {isRunning && <span className="animate-pulse text-zinc-500">_</span>}
      </div>
    </Card>
  )
}
