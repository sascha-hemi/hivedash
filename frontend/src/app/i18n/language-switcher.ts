import { Component, inject } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { TranslateService } from '@ngx-translate/core';

import { AuthService } from '../core/auth.service';
import { LocaleService } from './locale.service';
import { LOCALE_LABELS, SUPPORTED_LOCALES, SupportedLocale } from './supported-locales';

/** Used both in the navbar (logged in) and on the login page (not yet authenticated) - the
 * effective language is always shown and switchable either way; only *persisting* the choice to
 * an account requires being logged in (LocaleService handles that distinction internally). */
@Component({
  selector: 'app-language-switcher',
  imports: [FormsModule],
  templateUrl: './language-switcher.html',
})
export class LanguageSwitcher {
  private readonly translate = inject(TranslateService);
  private readonly localeService = inject(LocaleService);
  protected readonly auth = inject(AuthService);

  protected readonly locales = SUPPORTED_LOCALES;
  protected readonly labels = LOCALE_LABELS;

  get currentLang(): string {
    return this.translate.currentLang() ?? '';
  }

  async onChange(value: string): Promise<void> {
    if (value === 'auto') {
      await this.localeService.setLocale(null);
    } else {
      await this.localeService.setLocale(value as SupportedLocale);
    }
  }
}
