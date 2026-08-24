import { ApplicationConfig, provideBrowserGlobalErrorListeners } from '@angular/core';
import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { provideRouter } from '@angular/router';
import { provideTranslateService } from '@ngx-translate/core';

import { routes } from './app.routes';
import { authInterceptor } from './core/auth.interceptor';
import { FALLBACK_LOCALE } from './i18n/supported-locales';

export const appConfig: ApplicationConfig = {
  providers: [
    provideBrowserGlobalErrorListeners(),
    provideRouter(routes),
    provideHttpClient(withInterceptors([authInterceptor])),
    // Translations are registered directly (LocaleService.setTranslation for each supported
    // locale) rather than via an HTTP loader - the whole translation set is a modest amount of
    // short strings, so bundling it beats an extra async round-trip (and a flash of
    // untranslated/blank UI) for every page load.
    provideTranslateService({ fallbackLang: FALLBACK_LOCALE }),
  ]
};
