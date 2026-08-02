import { setRequestLocale } from 'next-intl/server';
import { getTranslations } from 'next-intl/server';
import { HeroSection } from '@/components/landing/HeroSection';
import { MetricsGrid } from '@/components/landing/MetricsGrid';
import { MethodologySection } from '@/components/landing/MethodologySection';

export default async function LandingPage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  setRequestLocale(locale);
  const t = await getTranslations();

  return (
    <div>
      <HeroSection />
      <MetricsGrid />
      <MethodologySection />
      <footer className="border-t border-border py-8 mt-20">
        <div className="max-w-6xl mx-auto px-6 text-center text-sm text-zinc-600">
          {t('Footer.copyright')}
        </div>
      </footer>
    </div>
  );
}
