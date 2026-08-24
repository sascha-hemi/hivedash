import { de } from './de';
import { en } from './en';
import { es } from './es';
import { fr } from './fr';
import { nl } from './nl';
import { Translations } from './translations';

export type SupportedLocale = 'en' | 'de' | 'nl' | 'es' | 'fr';

export const SUPPORTED_LOCALES: SupportedLocale[] = ['en', 'de', 'nl', 'es', 'fr'];

export const FALLBACK_LOCALE: SupportedLocale = 'en';

export const LOCALE_LABELS: Record<SupportedLocale, string> = {
  en: 'English',
  de: 'Deutsch',
  nl: 'Nederlands',
  es: 'Español',
  fr: 'Français',
};

export const TRANSLATIONS: Record<SupportedLocale, Translations> = { en, de, nl, es, fr };

export function isSupportedLocale(value: string | null | undefined): value is SupportedLocale {
  return !!value && (SUPPORTED_LOCALES as string[]).includes(value);
}
