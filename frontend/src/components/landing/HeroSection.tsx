import { Play } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { Link } from '@/i18n/navigation';

export function HeroSection() {
  const t = useTranslations('Hero');

  return (
    <section className="bg-zinc-950">
      <div className="max-w-6xl mx-auto px-6 pt-24 pb-8 text-center relative">
        <div className="absolute top-16 right-8">
          <span className="text-[10px] py-1 px-3 rounded-full border border-white/5 text-zinc-600">
            {t('version')}
          </span>
        </div>

        <h1 className="text-4xl md:text-6xl font-bold tracking-tight text-red-400">
          {t('title')}
        </h1>

        <p className="mt-6 text-lg text-zinc-400 max-w-xl mx-auto leading-relaxed">
          {t('subtitle')}
        </p>

        <div className="mt-8">
          <Link
            href="/runner"
            className="inline-flex items-center gap-2 px-6 py-3 rounded-lg bg-red-500 hover:bg-red-600 text-white font-medium text-sm transition-colors"
          >
            <Play className="size-4" />
            {t('cta_run')}
          </Link>
        </div>
      </div>
    </section>
  );
}
