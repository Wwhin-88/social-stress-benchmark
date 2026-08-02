import { useTranslations } from 'next-intl';
import {
  MessageSquare,
  GitBranch,
  AlertTriangle,
  Shield,
  Info,
} from 'lucide-react';
import { Card, CardHeader, CardContent } from '@/components/ui/card';

export function MethodologySection() {
  const t = useTranslations('Methodology');

  const subtests = [
    {
      icon: MessageSquare,
      key: 'subtest_1',
      badgeVariant: 'bg-red-500/10 text-red-400 border-red-500/20',
    },
    {
      icon: GitBranch,
      key: 'subtest_2',
      badgeVariant: 'bg-red-500/10 text-red-400 border-red-500/20',
    },
    {
      icon: AlertTriangle,
      key: 'subtest_3',
      badgeVariant: 'bg-red-500/10 text-red-400 border-red-500/20',
    },
  ] as const;

  return (
    <section className="py-20">
      <div className="max-w-6xl mx-auto px-6">
        <h2 className="text-3xl font-bold text-foreground text-center">
          {t('title')}
        </h2>

        <div className="mt-12 grid grid-cols-1 md:grid-cols-3 gap-6">
          {subtests.map(({ icon: Icon, key, badgeVariant }) => (
            <Card key={key} className="border-zinc-800 bg-zinc-950/60">
              <CardHeader>
                <div className="flex items-start gap-3">
                  <div className="flex size-10 items-center justify-center rounded-lg bg-red-500/10 shrink-0">
                    <Icon className="size-5 text-red-400" />
                  </div>
                  <div>
                    <h3 className="font-semibold text-foreground leading-snug">
                      {t(`${key}_title`)}
                    </h3>
                  </div>
                </div>
              </CardHeader>
              <CardContent>
                <p className="text-sm text-zinc-400 leading-relaxed">
                  {t(`${key}_desc`)}
                </p>
                <span
                  className={`mt-3 inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-medium ${badgeVariant}`}
                >
                  {t(`${key}_badge`)}
                </span>
              </CardContent>
            </Card>
          ))}
        </div>

        <div className="mt-8 rounded-xl border border-red-600/20 bg-red-500/5 p-6">
          <div className="flex items-start gap-3">
            <Shield className="size-5 text-red-400 shrink-0 mt-0.5" />
            <div>
              <h4 className="font-semibold text-foreground text-sm">
                {t('gate_title')}
              </h4>
              <p className="mt-1 text-sm text-zinc-400 leading-relaxed">
                {t('gate_desc')}
              </p>
              <p className="mt-2 text-sm text-zinc-400 leading-relaxed">
                {t('composite_desc')}
              </p>
            </div>
          </div>
        </div>

        <div className="mt-6 rounded-xl border border-red-600/20 bg-red-500/5 p-6">
          <div className="flex items-start gap-3">
            <Info className="size-5 text-red-400 shrink-0 mt-0.5" />
            <div>
              <h4 className="font-semibold text-foreground text-sm">
                {t('data_types_title')}
              </h4>
              <p className="mt-1 text-sm text-zinc-400 leading-relaxed">
                {t('data_types_desc')}
              </p>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
