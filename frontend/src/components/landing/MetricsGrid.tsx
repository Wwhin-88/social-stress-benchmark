import { useTranslations } from 'next-intl';
import { METRICS } from '@/lib/metrics';
import { MetricCard } from './MetricCard';

export function MetricsGrid() {
  const t = useTranslations('Metrics');

  return (
    <section id="metrics" className="py-20">
      <div className="max-w-6xl mx-auto px-6">
        <h2 className="text-2xl font-bold text-foreground text-center">
          {t('title')}

        </h2>

        <div className="mt-12 grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
          {METRICS.map((metric) => (
            <MetricCard key={metric.code} code={metric.code} />
          ))}
        </div>
      </div>
    </section>
  );
}
