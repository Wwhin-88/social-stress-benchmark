import { useTranslations } from 'next-intl';
import { Shield, BrainCircuit, Handshake, Swords, Flag, Lightbulb, Heart, EyeOff, Book, Layers, Crown, Smile, Zap } from 'lucide-react';
import type { MetricCode } from '@/lib/metrics';
import { cn } from '@/lib/utils';

const iconMap: Record<MetricCode, React.ComponentType<{ className?: string }>> = {
  DV: Shield,
  MD: BrainCircuit,
  SY: Handshake,
  AS: Swords,
  AC_cap: Flag,
  PS: Lightbulb,
  AA: Heart,
  EV: EyeOff,
  IN: Book,
  CD: Layers,
  PL: Crown,
  BN: Smile,
  AG: Zap,
};

const badgeClasses: Record<string, string> = {
  DV: 'bg-red-500/10 text-red-400 border-red-500/20',
  negative: 'bg-zinc-800 text-zinc-400 border-zinc-700',
  positive: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20',
};

interface MetricCardProps {
  code: MetricCode;
}

export function MetricCard({ code }: MetricCardProps) {
  const t = useTranslations('Metrics');
  const Icon = iconMap[code];

  const badgeVariant = code === 'DV'
    ? 'DV'
    : code === 'AC_cap' || code === 'MD' || code === 'SY' || code === 'EV' || code === 'IN' || code === 'AG'
      ? 'negative'
      : 'positive';

  return (
    <div
      className={cn(
        'group rounded-xl border border-border bg-card p-5 transition-colors hover:border-cyan-500/30',
      )}
    >
      <div className="flex items-start justify-between">
        <div className="flex size-12 items-center justify-center rounded-lg bg-cyan-500/10">
          <Icon className="size-5 text-cyan-400" />
        </div>
        <span
          className={cn(
            'inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium',
            badgeClasses[badgeVariant],
          )}
        >
          {code.replace('_cap', '')}
        </span>
      </div>

      <h3 className="mt-4 font-semibold text-foreground">
        {t(`${code}_name`)}
      </h3>

      <p className="mt-1.5 text-sm text-muted-foreground leading-relaxed">
        {t(`${code}_desc`)}
      </p>
    </div>
  );
}
