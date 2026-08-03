'use client'

import { useState } from 'react'
import { useTranslations } from 'next-intl'
import { Cpu, Play, ScrollText, SearchCheck, Shield, Eye, EyeOff, Key } from 'lucide-react'
import { Checkbox } from '@/components/ui/checkbox'

const SCENARIO_OPTIONS = [
  { id: 'smart_home_vendetta', labelKey: 'scenario_smart_home' },
  { id: 'smart_home_vendetta_v2', labelKey: 'scenario_smart_home_v2' },
]

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

export function ConfigPanel() {
  const t = useTranslations('Runner')

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
    if (selectedScenarios.size === SCENARIO_OPTIONS.length) {
      setSelectedScenarios(new Set())
    } else {
      setSelectedScenarios(new Set(SCENARIO_OPTIONS.map((s) => s.id)))
    }
  }

  const toggleAllSubtests = () => {
    if (selectedSubtests.size === SUBTEST_OPTIONS.length) {
      setSelectedSubtests(new Set())
    } else {
      setSelectedSubtests(new Set(SUBTEST_OPTIONS.map((s) => s.id)))
    }
  }

  const areAllScenariosSelected = selectedScenarios.size === SCENARIO_OPTIONS.length
  const areAllSubtestsSelected = selectedSubtests.size === SUBTEST_OPTIONS.length

  return (
    <div className="flex flex-col gap-5 bg-card rounded-xl ring-1 ring-foreground/10 p-5 text-sm">
      <h2 className="text-xs uppercase tracking-wide text-muted-foreground">
        {t('config_title')}
      </h2>

      <div className="space-y-1.5">
        <label className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-zinc-500">
          <SearchCheck className="size-3" />
          {t('reviewer_model')}
        </label>
        <input
          type="text"
          placeholder="deepseek-v4-flash"
          className="w-full bg-zinc-900 border border-border rounded-lg px-3 py-2 text-sm text-zinc-200
            placeholder:text-muted-foreground
            focus:outline-none focus:ring-1 focus:ring-red-400/50 focus:border-red-400/30"
        />
        <div className="relative">
          <input
            type={showReviewerKey ? 'text' : 'password'}
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
      </div>

      <div className="space-y-1.5">
        <label className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-zinc-500">
          <Cpu className="size-3" />
          {t('target_model')}
        </label>
        <input
          type="text"
          placeholder="gpt-5.2"
          className="w-full bg-zinc-900 border border-border rounded-lg px-3 py-2 text-sm text-zinc-200
            placeholder:text-muted-foreground
            focus:outline-none focus:ring-1 focus:ring-red-400/50 focus:border-red-400/30"
        />
        <div className="relative">
          <input
            type={showTargetKey ? 'text' : 'password'}
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
          {SCENARIO_OPTIONS.map((scenario) => (
            <label
              key={scenario.id}
              className="flex items-start gap-2 px-2 py-1.5 rounded-lg cursor-pointer
                hover:bg-zinc-900/50 transition-colors"
            >
              <Checkbox
                checked={selectedScenarios.has(scenario.id)}
                onCheckedChange={() => toggleScenario(scenario.id)}
              />
              <span className="text-xs text-zinc-400 leading-relaxed pt-px">
                {t(scenario.labelKey as any)}
              </span>
            </label>
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
            <label
              key={subtest.id}
              className="flex items-center gap-2 px-2 py-1.5 rounded-lg cursor-pointer
                hover:bg-zinc-900/50 transition-colors"
            >
              <Checkbox
                checked={selectedSubtests.has(subtest.id)}
                onCheckedChange={() => toggleSubtest(subtest.id)}
              />
              <span className="text-xs text-zinc-400 pt-px">
                {t(subtest.labelKey as any)}
              </span>
            </label>
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

      <button className="w-full flex items-center justify-center gap-2 bg-red-600 hover:bg-red-700 text-white font-medium rounded-lg px-4 py-2.5 text-sm transition-colors cursor-pointer">
        <Play className="size-4" fill="currentColor" />
        {t('run_button')}
      </button>
    </div>
  )
}
