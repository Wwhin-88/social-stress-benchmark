'use client'

import { useState, useCallback, useEffect } from 'react'
import { ConfigPanel } from './ConfigPanel'
import type { RunConfigFromPanel } from './ConfigPanel'
import { TerminalOutput } from './TerminalOutput'
import { RadarChart } from './RadarChart'
import type { RadarRow } from './RadarChart'
import { startRun, fetchScenarios, fetchRun, createRunStream } from '@/lib/api'
import type { ScenarioItem } from '@/lib/api'

export function RunnerClient() {
  const [scenarios, setScenarios] = useState<ScenarioItem[]>([])
  const [runId, setRunId] = useState<string | null>(null)
  const [isRunning, setIsRunning] = useState(false)
  const [logs, setLogs] = useState<Array<{ text: string; color: string }>>([])
  const [result, setResult] = useState<RadarRow[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetchScenarios()
      .then((data) => setScenarios(data.scenarios))
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
  }, [])

  const addLog = useCallback((text: string, color: string) => {
    setLogs((prev) => [...prev, { text, color }])
  }, [])

  const handleRun = useCallback(
    async (config: RunConfigFromPanel) => {
      setError(null)
      setResult(null)
      setLogs([])
      setIsRunning(true)

      try {
        const response = await startRun({
          provider: config.provider,
          model: config.model,
          api_key: config.api_key,
          api_base: config.api_base || undefined,
          max_tokens: config.max_tokens ?? null,
          temperature: config.temperature ?? null,
          reviewer_provider: config.reviewer_provider,
          reviewer_model: config.reviewer_model,
          reviewer_api_key: config.reviewer_api_key,
          reviewer_api_base: config.reviewer_api_base || undefined,
          scenarios: config.scenarios,
          subtests: config.subtests.length > 0 ? config.subtests : null,
          defender_variant: config.defender_variant,
        })

        const rid = response.run_id
        setRunId(rid)

        const es = createRunStream(rid)

        es.addEventListener('run_start', () => {
          addLog('$ ssb run --profile quick', 'text-zinc-500')
        })

        es.addEventListener('config', (event: MessageEvent) => {
          try {
            const data = JSON.parse(event.data)
            const reviewer = data.reviewer_model ?? data.reviewer ?? '?'
            const scenario = data.scenario ?? '?'
            const defender = data.defender_variant ?? data.defender ?? '?'
            addLog(
              `\u2713 Reviewer: ${reviewer} \u00b7 Scenario: ${scenario} \u00b7 Defender: ${defender}`,
              'text-emerald-500'
            )
          } catch {
            addLog('\u2713 Config loaded', 'text-emerald-500')
          }
        })

        es.addEventListener('llm_call', (event: MessageEvent) => {
          try {
            const data = JSON.parse(event.data)
            const subtest = data.subtest ?? '?'
            const turn = data.turn ?? '?'
            addLog(
              `\u2192 ${subtest}/turn ${turn} complete`,
              'text-red-400'
            )
          } catch {
            addLog('\u2192 LLM call complete', 'text-red-400')
          }
        })

        es.addEventListener('reviewer_eval', (event: MessageEvent) => {
          try {
            const data = JSON.parse(event.data)
            const turn = data.turn ?? '?'
            const latency = data.latency_ms ?? data.latency ?? '?'
            addLog(
              `  Turn ${turn} evaluated (${latency}ms)`,
              'text-zinc-400'
            )
          } catch {
            addLog('  Evaluation complete', 'text-zinc-400')
          }
        })

        es.addEventListener('choice', (event: MessageEvent) => {
          try {
            const data = JSON.parse(event.data)
            const subtest = data.subtest ?? '?'
            const dp = data.decision_point ?? data.dp ?? '?'
            const chosen = data.chosen ?? '?'
            addLog(
              `  ${subtest}/dp${dp}: ${chosen}`,
              'text-zinc-400'
            )
          } catch {
            addLog('  Choice recorded', 'text-zinc-400')
          }
        })

        es.addEventListener('scoring', (event: MessageEvent) => {
          try {
            const data = JSON.parse(event.data)
            const composite = data.composite_score ?? '?'
            const gate = data.gate ?? data.gate_passed ?? false
            const gateStr = typeof gate === 'boolean'
              ? (gate ? 'PASSED' : 'FAILED')
              : String(gate)
            const color = gateStr === 'PASSED' || gateStr === 'passed'
              ? 'text-emerald-500'
              : 'text-red-400'
            addLog(
              `  Composite Score: ${composite} \u00b7 Gate: ${gateStr}`,
              color
            )
          } catch {
            addLog('  Scoring complete', 'text-zinc-400')
          }
        })

        es.addEventListener('error', (event: MessageEvent) => {
          try {
            const data = JSON.parse(event.data)
            const errorType = data.error_type ?? 'error'
            const message = data.message ?? 'Unknown error'
            addLog(`  [${errorType}] ${message}`, 'text-red-500')
          } catch {
            addLog('  Error occurred', 'text-red-500')
          }
        })

        es.addEventListener('run_end', async () => {
          addLog('\u2713 Benchmark complete', 'text-emerald-500')
          es.close()
          setIsRunning(false)
          try {
            const runResult = await fetchRun(rid)
            const parsed = JSON.parse(runResult.result_json)
            const radarRows = buildRadarRows(parsed)
            setResult(radarRows)
          } catch (e) {
            setError(e instanceof Error ? e.message : String(e))
          }
        })

        es.onerror = () => {
          addLog('Connection error', 'text-red-500')
          es.close()
          setIsRunning(false)
          setError('SSE connection error')
        }
      } catch (e) {
        setIsRunning(false)
        setError(e instanceof Error ? e.message : String(e))
      }
    },
    [addLog]
  )

  return (
    <div className="flex gap-6 items-start">
      <div className="w-[360px] shrink-0">
        <ConfigPanel
          scenarios={scenarios}
          onRun={handleRun}
          isRunning={isRunning}
        />
      </div>
      <div className="flex-1 min-w-0 space-y-6">
        {error && (
          <div className="bg-red-500/10 border border-red-500/20 rounded-lg px-4 py-3 text-sm text-red-400">
            {error}
          </div>
        )}
        <TerminalOutput logs={logs} isRunning={isRunning} />
        <RadarChart data={result} />
      </div>
    </div>
  )
}

function buildRadarRows(parsed: Record<string, unknown>): RadarRow[] {
  const metrics = ['DV', 'MD', 'SY', 'AS', 'AC_cap', 'PS', 'AA', 'EV', 'IN', 'CD', 'PL', 'BN', 'AG']
  const positiveMetrics = new Set(['AS', 'PS', 'AA', 'CD', 'PL', 'BN'])

  const subtest1 = (parsed.subtest_1 as Record<string, unknown>) ?? {}
  const reviewerScores =
    (subtest1.reviewer_scores as Record<string, { score: number }>) ?? {}

  return metrics.map((code) => {
    const scoreEntry = reviewerScores[code]
    const modelScore = scoreEntry?.score ?? 0
    const baselineScore = positiveMetrics.has(code) ? 4 : 0
    return { metric: code, model: modelScore, baseline: baselineScore }
  })
}
