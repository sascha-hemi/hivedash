import { Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';

import { AuthService } from '../../core/auth.service';
import { LanguageSwitcher } from '../../i18n/language-switcher';

@Component({
  selector: 'app-login',
  imports: [FormsModule, TranslatePipe, LanguageSwitcher],
  templateUrl: './login.html',
  styleUrl: './login.scss',
})
export class LoginPage implements OnInit {
  private readonly auth = inject(AuthService);
  private readonly router = inject(Router);
  private readonly translate = inject(TranslateService);

  email = '';
  password = '';
  readonly submitting = signal(false);
  readonly error = signal<string | null>(null);
  readonly oidcEnabled = signal(false);

  async ngOnInit(): Promise<void> {
    this.oidcEnabled.set(await this.auth.oidcEnabled().catch(() => false));
  }

  async submit(): Promise<void> {
    this.error.set(null);
    this.submitting.set(true);
    try {
      await this.auth.login(this.email, this.password);
      await this.router.navigateByUrl('/');
    } catch {
      this.error.set(this.translate.instant('login.invalidCredentials'));
    } finally {
      this.submitting.set(false);
    }
  }

  loginWithOidc(): void {
    window.location.href = '/api/auth/oidc/login';
  }
}
