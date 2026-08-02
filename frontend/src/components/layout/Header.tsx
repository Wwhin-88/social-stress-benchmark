import { Link } from '@/i18n/navigation';
import { getTranslations } from 'next-intl/server';
import { LanguageSwitcher } from './LanguageSwitcher';
import { FlaskConical, Play } from 'lucide-react';

export async function Header() {
  const t = await getTranslations('Nav');

  return (
    <header className="sticky top-0 z-50 border-b border-white/5 bg-zinc-950/80 backdrop-blur-md">
      <div className="max-w-7xl mx-auto flex items-center justify-between px-6 h-14">
        <Link
          href="/"
          className="flex items-center gap-2 font-semibold text-red-400 hover:text-red-300 transition-colors"
        >
          <FlaskConical className="h-5 w-5" />
          <span className="text-sm tracking-tight">{t('home')}</span>
        </Link>

        <nav className="flex items-center gap-1">
          <Link
            href="/runner"
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm text-zinc-400 hover:text-zinc-200 hover:bg-white/5 transition-colors"
          >
            <Play className="h-3.5 w-3.5" />
            {t('runner')}
          </Link>
        </nav>

        <div className="flex items-center gap-3">
          <LanguageSwitcher />
        </div>
      </div>
    </header>
  );
}
