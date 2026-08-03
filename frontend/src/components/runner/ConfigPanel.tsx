'use client'

import { useState } from 'react'
import { useTranslations } from 'next-intl'
import { Cpu, Play, ScrollText, SearchCheck, Shield, Eye, EyeOff, Key } from 'lucide-react'
import { Checkbox } from '@/components/ui/checkbox'
import type { ScenarioItem } from '@/lib/api'

export interface RunConfigFromPanel {
  provider: string
  model: string
  api_key: string
  api_base: string
  max_tokens: number | null
  temperature: number | null
  reviewer_provider: string
  reviewer_model: string
  reviewer_api_key: string
  reviewer_api_base: string
  scenarios: string[]
  subtests: string[]
  defender_variant: string
}

interface ConfigPanelProps {
  scenarios: ScenarioItem[]
  onRun: (config: RunConfigFromPanel) => void
  isRunning: boolean
}

const SUBTEST_OPTIONS = [
  { id: 'subtest_1', labelKey: 'subtest_1_label' },
  { id: 'subtest_2', labelKey: 'subtest_2_label' },
  { id: 'subtest_3', labelKey: 'subtest_3_label' },
]

const DEFENDER_VARIANTS = ['all', 'weak', 'normal', 'aggressive'] as const

function SectionHeader({
  icon: Icon,
  label,
  actionLabel,
  onAction,
  actionActive,
}: {
  icon: React.ComponentType<{ className?: string }>
  label: string
  actionLabel?: string
  onAction?: () => void
  actionActive?: boolean
}) {
  return (
    <div className="flex items-center justify-between mb-2">
      <label className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-zinc-500">
        <Icon className="size-3" />
        {label}
      </label>
      {actionLabel && onAction && (
        <button
          type="button"
          onClick={onAction}
          className={`text-[10px] font-medium uppercase tracking-wider transition-colors cursor-pointer ${
            actionActive
              ? 'text-red-400 hover:text-red-300'
              : 'text-muted-foreground hover:text-zinc-300'
          }`}
        >
          {actionLabel}
        </button>
      )}
    </div>
  )
}

export function ConfigPanel({ scenarios, onRun, isRunning }: ConfigPanelProps) {
  const t = useTranslations('Runner')

  const [provider, setProvider] = useState('')
  const [model, setModel] = useState('')
  const [apiKey, setApiKey] = useState('')
  const [apiBase, setApiBase] = useState('')
  const [maxTokens, setMaxTokens] = useState('')
  const [temperature, setTemperature] = useState('')
  const [reviewerProvider, setReviewerProvider] = useState('')
  const [reviewerModel, setReviewerModel] = useState('')
  const [reviewerApiKey, setReviewerApiKey] = useState('')
  const [reviewerApiBase, setReviewerApiBase] = useState('')
  const [useCustomTokens, setUseCustomTokens] = useState(false)
  const [useCustomTemp, setUseCustomTemp] = useState(false)
  const [showReviewerKey, setShowReviewerKey] = useState(false)
  const [showTargetKey, setShowTargetKey] = useState(false)
  const [selectedScenarios, setSelectedScenarios] = useState<Set<string>>(new Set())
  const [selectedSubtests, setSelectedSubtests] = useState<Set<string>>(
    new Set(SUBTEST_OPTIONS.map((s) => s.id))
  )
  const [defenderVariant, setDefenderVariant] = useState<string>('normal')

  const toggleScenario = (id: string) => {
    setSelectedScenarios((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const toggleSubtest = (id: string) => {
    setSelectedSubtests((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const toggleAllScenarios = () => {
    if (selectedScenarios.size === scenarios.length) {
      setSelectedScenarios(new Set())
    } else {
      setSelectedScenarios(new Set(scenarios.map((s) => s.id)))
    }
  }

  const toggleAllSubtests = () => {
    if (selectedSubtests.size === SUBTEST_OPTIONS.length) {
      setSelectedSubtests(new Set())
    } else {
      setSelectedSubtests(new Set(SUBTEST_OPTIONS.map((s) => s.id)))
    }
  }

  const areAllScenariosSelected = scenarios.length > 0 && selectedScenarios.size === scenarios.length
  const areAllSubtestsSelected = selectedSubtests.size === SUBTEST_OPTIONS.length

  const handleSubmit = () => {
    const defVariant = defenderVariant === 'all' ? 'normal' : defenderVariant
    onRun({
      provider,
      model,
      api_key: apiKey,
      api_base: apiBase,
      max_tokens: useCustomTokens && maxTokens ? Number(maxTokens) : null,
      temperature: useCustomTemp && temperature ? Number(temperature) : null,
      reviewer_provider: reviewerProvider,
      reviewer_model: reviewerModel,
      reviewer_api_key: reviewerApiKey,
      reviewer_api_base: reviewerApiBase,
      scenarios: Array.from(selectedScenarios),
      subtests: Array.from(selectedSubtests),
      defender_variant: defVariant,
    })
  }

  return (
    <div className="flex flex-col gap-5 bg-card rounded-xl ring-1 ring-foreground/10 p-5 text-sm">
      <h2 className="text-xs uppercase tracking-wide text-muted-foreground">
        {t('config_title')}
      </h2>

      <div className="space-y-1.5">
        <label className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-zinc-500">
          <SearchCheck className="size-3" />
          {t('reviewer_provider')}
        </label>
        <input
          type="text"
          value={reviewerProvider}
          onChange={(e) => setReviewerProvider(e.target.value)}
          placeholder={t('placeholder_provider')}
          className="w-full bg-zinc-900 border border-border rounded-lg px-3 py-2 text-sm text-zinc-200
            placeholder:text-muted-foreground
            focus:outline-none focus:ring-1 focus:ring-red-400/50 focus:border-red-400/30"
        />
      </div>

      <div className="space-y-1.5">
        <label className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-zinc-500">
          <SearchCheck className="size-3" />
          {t('reviewer_model')}
        </label>
        <input
          type="text"
          value={reviewerModel}
          onChange={(e) => setReviewerModel(e.target.value)}
          placeholder="deepseek-v4-flash"
          className="w-full bg-zinc-900 border border-border rounded-lg px-3 py-2 text-sm text-zinc-200
            placeholder:text-muted-foreground
            focus:outline-none focus:ring-1 focus:ring-red-400/50 focus:border-red-400/30"
        />
        <div className="relative">
          <input
            type={showReviewerKey ? 'text' : 'password'}
            value={reviewerApiKey}
            onChange={(e) => setReviewerApiKey(e.target.value)}
            placeholder={t('placeholder_key')}
            className="w-full bg-zinc-900 border border-border rounded-lg pl-3 pr-9 py-2 text-sm font-mono
              placeholder:text-muted-foreground text-zinc-200
              focus:outline-none focus:ring-1 focus:ring-red-400/50"
          />
          <button
            type="button"
            onClick={() => setShowReviewerKey(!showReviewerKey)}
            className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground cursor-pointer"
          >
            {showReviewerKey ? <EyeOff className="size-3.5" /> : <Eye className="size-3.5" />}
          </button>
        </div>
        <input
          type="text"
          value={reviewerApiBase}
          onChange={(e) => setReviewerApiBase(e.target.value)}
          placeholder={t('placeholder_api_base')}
          className="w-full bg-zinc-900 border border-border rounded-lg px-3 py-2 text-sm text-zinc-200
            placeholder:text-muted-foreground
            focus:outline-none focus:ring-1 focus:ring-red-400/50 focus:border-red-400/30"
        />
      </div>

      <div className="space-y-1.5">
        <label className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-zinc-500">
          <Cpu className="size-3" />
          {t('target_provider')}
        </label>
        <input
          type="text"
          value={provider}
          onChange={(e) => setProvider(e.target.value)}
          placeholder={t('placeholder_provider')}
          className="w-full bg-zinc-900 border border-border rounded-lg px-3 py-2 text-sm text-zinc-200
            placeholder:text-muted-foreground
            focus:outline-none focus:ring-1 focus:ring-red-400/50 focus:border-red-400/30"
        />
      </div>

      <div className="space-y-1.5">
        <label className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-zinc-500">
          <Cpu className="size-3" />
          {t('target_model')}
        </label>
        <input
          type="text"
          value={model}
          onChange={(e) => setModel(e.target.value)}
          placeholder="gpt-5.2"
          className="w-full bg-zinc-900 border border-border rounded-lg px-3 py-2 text-sm text-zinc-200
            placeholder:text-muted-foreground
            focus:outline-none focus:ring-1 focus:ring-red-400/50 focus:border-red-400/30"
        />
        <div className="relative">
          <input
            type={showTargetKey ? 'text' : 'password'}
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
            placeholder={t('placeholder_key')}
            className="w-full bg-zinc-900 border border-border rounded-lg pl-3 pr-9 py-2 text-sm font-mono
              placeholder:text-muted-foreground text-zinc-200
              focus:outline-none focus:ring-1 focus:ring-red-400/50"
          />
          <button
            type="button"
            onClick={() => setShowTargetKey(!showTargetKey)}
            className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground cursor-pointer"
          >
            {showTargetKey ? <EyeOff className="size-3.5" /> : <Eye className="size-3.5" />}
          </button>
        </div>
        <input
          type="text"
          value={apiBase}
          onChange={(e) => setApiBase(e.target.value)}
          placeholder={t('placeholder_api_base')}
          className="w-full bg-zinc-900 border border-border rounded-lg px-3 py-2 text-sm text-zinc-200
            placeholder:text-muted-foreground
            focus:outline-none focus:ring-1 focus:ring-red-400/50 focus:border-red-400/30"
        />
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-xs text-zinc-400">{t('max_tokens')}</span>
            <button
              type="button"
              onClick={() => setUseCustomTokens(!useCustomTokens)}
              className={`text-[10px] font-medium uppercase tracking-wider transition-colors cursor-pointer ${
                useCustomTokens ? 'text-red-400' : 'text-muted-foreground hover:text-zinc-300'
              }`}
            >
              {useCustomTokens ? t('custom') : t('default')}
            </button>
          </div>
          {useCustomTokens && (
            <input
              type="number"
              min={1}
              value={maxTokens}
              onChange={(e) => setMaxTokens(e.target.value)}
              placeholder={t('placeholder_max_tokens')}
              className="w-full bg-zinc-900 border border-border rounded-lg px-3 py-2 text-sm text-zinc-200
                placeholder:text-muted-foreground
                focus:outline-none focus:ring-1 focus:ring-red-400/50"
            />
          )}
        </div>
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-xs text-zinc-400">{t('temperature')}</span>
            <button
              type="button"
              onClick={() => setUseCustomTemp(!useCustomTemp)}
              className={`text-[10px] font-medium uppercase tracking-wider transition-colors cursor-pointer ${
                useCustomTemp ? 'text-red-400' : 'text-muted-foreground hover:text-zinc-300'
              }`}
            >
              {useCustomTemp ? t('custom') : t('default')}
            </button>
          </div>
          {useCustomTemp && (
            <input
              type="number"
              min={0}
              max={2}
              step={0.1}
              value={temperature}
              onChange={(e) => setTemperature(e.target.value)}
              placeholder={t('placeholder_temperature')}
              className="w-full bg-zinc-900 border border-border rounded-lg px-3 py-2 text-sm text-zinc-200
                placeholder:text-muted-foreground
                focus:outline-none focus:ring-1 focus:ring-red-400/50"
            />
          )}
        </div>
      </div>

      <div className="space-y-1.5">
        <SectionHeader
          icon={ScrollText}
          label={t('scenarios_label')}
          actionLabel={areAllScenariosSelected ? t('deselect_all') : t('select_all')}
          onAction={toggleAllScenarios}
          actionActive={selectedScenarios.size > 0}
        />
        <div className="space-y-1">
          {scenarios.map((scenario) => (
            <div
              key={scenario.id}
              onClick={() => toggleScenario(scenario.id)}
              className="flex items-start gap-2 px-2 py-1.5 rounded-lg cursor-pointer
                hover:bg-zinc-900/50 transition-colors"
            >
              <Checkbox
                checked={selectedScenarios.has(scenario.id)}
              />
              <span className="text-xs text-zinc-400 leading-relaxed pt-px">
                {scenario.name}
              </span>
            </div>
          ))}
        </div>
        <div className="text-[10px] text-red-400/70 font-medium">
          {t('selected_count', { count: selectedScenarios.size })}
        </div>
      </div>

      <div className="space-y-1.5">
        <SectionHeader
          icon={ScrollText}
          label={t('subtests_label')}
          actionLabel={areAllSubtestsSelected ? t('deselect_all') : t('select_all')}
          onAction={toggleAllSubtests}
          actionActive={selectedSubtests.size > 0}
        />
        <div className="space-y-0.5">
          {SUBTEST_OPTIONS.map((subtest) => (
            <div
              key={subtest.id}
              onClick={() => toggleSubtest(subtest.id)}
              className="flex items-center gap-2 px-2 py-1.5 rounded-lg cursor-pointer
                hover:bg-zinc-900/50 transition-colors"
            >
              <Checkbox
                checked={selectedSubtests.has(subtest.id)}
              />
              <span className="text-xs text-zinc-400 pt-px">
                {t(subtest.labelKey as any)}
              </span>
            </div>
          ))}
        </div>
      </div>

      <div className="space-y-2">
        <label className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-zinc-500">
          <Shield className="size-3" />
          {t('defender_label')}
        </label>
        <div className="grid grid-cols-2 gap-0.5 rounded-lg bg-zinc-900 p-0.5">
          {DEFENDER_VARIANTS.map((variant) => {
            const isActive = defenderVariant === variant
            return (
              <button
                key={variant}
                type="button"
                onClick={() => setDefenderVariant(variant)}
                className={`whitespace-nowrap text-center text-xs font-medium py-1.5 rounded-md transition-all cursor-pointer ${
                  isActive
                    ? 'bg-red-500/10 text-red-400 ring-1 ring-red-500/20'
                    : 'text-zinc-500 hover:text-zinc-300'
                }`}
              >
                {t(`variants.${variant}` as any)}
              </button>
            )
          })}
        </div>
      </div>

      <button
        onClick={handleSubmit}
        disabled={isRunning || selectedScenarios.size === 0}
        className="w-full flex items-center justify-center gap-2 bg-red-600 hover:bg-red-700 text-white font-medium rounded-lg px-4 py-2.5 text-sm transition-colors cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
      >
        <Play className="size-4" fill="currentColor" />
        {isRunning ? t('running') : t('run_button')}
      </button>
    </div>
  )
}
