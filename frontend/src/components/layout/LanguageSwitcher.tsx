'use client';

import { useTransition } from 'react';
import { useLocale, useTranslations } from 'next-intl';
import { usePathname, useRouter } from '@/i18n/navigation';
import { routing } from '@/i18n/routing';
import { Globe } from 'lucide-react';
import { cn } from '@/lib/utils';

export function LanguageSwitcher() {
  const router = useRouter();
  const [isPending, startTransition] = useTransition();
  const pathname = usePathname();
  const currentLocale = useLocale();
  const t = useTranslations('Nav');

  function switchTo(nextLocale: string) {
    startTransition(() => {
      router.replace({ pathname }, { locale: nextLocale });
    });
  }

  const otherLocale = routing.locales.find((l) => l !== currentLocale) || 'en';

  return (
    <button
      onClick={() => switchTo(otherLocale)}
      disabled={isPending}
      className={cn(
        'flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium',
        'border border-white/10 text-zinc-400 hover:text-zinc-200 hover:border-white/20',
        'transition-colors',
        isPending && 'opacity-50'
      )}
    >
      <Globe className="h-3.5 w-3.5" />
      {t(otherLocale)}
    </button>
  );
}
