import { HttpClient } from '@angular/common/http';
import { Injectable, effect, inject } from '@angular/core';
import { TranslateService, TranslationObject } from '@ngx-translate/core';
import { firstValueFrom } from 'rxjs';

import { AuthService } from '../core/auth.service';
import { CurrentUser } from '../core/models';
import {
  FALLBACK_LOCALE,
  SUPPORTED_LOCALES,
  SupportedLocale,
  TRANSLATIONS,
  isSupportedLocale,
} from './supported-locales';

const STORAGE_KEY = 'hivedash.locale';

/** Auto-detects a language on first load (browser languages first, then localStorage cache,
 * then the fallback), applies it immediately so even the pre-login pages are translated, and
 * switches to the account's explicit choice as soon as one is known (login, or fetchMe() at
 * bootstrap) - an explicit account preference always wins over auto-detection, but only once
 * the account actually has one; until then, auto-detection keeps being the effective language
 * (e.g. if the browser's own language setting changes between visits). */
@Injectable({ providedIn: 'root' })
export class LocaleService {
  private readonly translate = inject(TranslateService);
  private readonly auth = inject(AuthService);
  private readonly http = inject(HttpClient);

  constructor() {
    for (const locale of SUPPORTED_LOCALES) {
      this.translate.setTranslation(locale, TRANSLATIONS[locale] as unknown as TranslationObject);
    }
    this.translate.use(this.detectInitialLocale());

    // Reacts to login/fetchMe/logout - an account-level locale always wins once known. Logging
    // out (user becomes null) deliberately leaves the current language alone rather than
    // resetting it - the browser/local-storage-detected language is still the right guess.
    effect(() => {
      const user = this.auth.user();
      if (user?.locale && isSupportedLocale(user.locale)) {
        this.translate.use(user.locale);
      }
    });
  }

  /** Available for a language switcher (navbar, login page). Persists to the account when
   * logged in; always cached in localStorage too, so the login page keeps a manual choice
   * across a logout/reload even though there's no account to attach it to yet. */
  async setLocale(locale: SupportedLocale | null): Promise<void> {
    const effective = locale ?? this.detectBrowserLocale();
    this.translate.use(effective);

    if (locale) {
      localStorage.setItem(STORAGE_KEY, locale);
    } else {
      localStorage.removeItem(STORAGE_KEY);
    }

    const user = this.auth.user();
    if (user) {
      await this.persist(locale);
    }
  }

  private async persist(locale: SupportedLocale | null): Promise<void> {
    try {
      const updated = await firstValueFrom(
        this.http.patch<CurrentUser>('/api/auth/me', { locale }),
      );
      this.auth.setUserLocale(updated.locale);
    } catch {
      // best-effort - the language still switched for this session, it just didn't persist;
      // not worth surfacing an error banner for.
    }
  }

  private detectInitialLocale(): SupportedLocale {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (isSupportedLocale(stored)) return stored;
    return this.detectBrowserLocale();
  }

  private detectBrowserLocale(): SupportedLocale {
    const candidates = navigator.languages?.length ? navigator.languages : [navigator.language];
    for (const candidate of candidates) {
      const base = candidate.split('-')[0].toLowerCase();
      if (isSupportedLocale(base)) return base;
    }
    return FALLBACK_LOCALE;
  }
}
