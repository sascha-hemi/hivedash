import { HttpClient } from '@angular/common/http';
import { Injectable, computed, inject, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';

import { CurrentUser } from './models';

@Injectable({ providedIn: 'root' })
export class AuthService {
  private readonly http = inject(HttpClient);

  private readonly _user = signal<CurrentUser | null>(null);
  private readonly _checked = signal(false);

  readonly user = this._user.asReadonly();
  readonly checked = this._checked.asReadonly();
  readonly isAdmin = computed(() => this._user()?.role === 'admin');

  /** Called once at app bootstrap to find out if a session cookie is already valid. */
  async fetchMe(): Promise<void> {
    try {
      const user = await firstValueFrom(this.http.get<CurrentUser>('/api/auth/me'));
      this._user.set(user);
    } catch {
      this._user.set(null);
    } finally {
      this._checked.set(true);
    }
  }

  async login(email: string, password: string): Promise<void> {
    const user = await firstValueFrom(
      this.http.post<CurrentUser>('/api/auth/login', { email, password }),
    );
    this._user.set(user);
  }

  async logout(): Promise<void> {
    try {
      await firstValueFrom(this.http.post('/api/auth/logout', {}));
    } finally {
      this._user.set(null);
    }
  }

  async oidcEnabled(): Promise<boolean> {
    const config = await firstValueFrom(
      this.http.get<{ oidc_enabled: boolean }>('/api/auth/config'),
    );
    return config.oidc_enabled;
  }

  /** Called by the 401 handler in auth.interceptor.ts. */
  clearUser(): void {
    this._user.set(null);
  }

  /** Called by LocaleService after PATCH /api/auth/me - updates the in-memory user without a
   * full re-fetch, so e.g. isAdmin() and everything else on the signal stays exactly as it was. */
  setUserLocale(locale: string | null): void {
    const current = this._user();
    if (current) {
      this._user.set({ ...current, locale });
    }
  }

  /** Self-service password change (see account.ts) - rejected server-side with 400 for an
   * OIDC-provisioned account (has_password false) and 401 if currentPassword is wrong. */
  async changePassword(currentPassword: string, newPassword: string): Promise<void> {
    await firstValueFrom(
      this.http.patch<CurrentUser>('/api/auth/me', {
        current_password: currentPassword,
        new_password: newPassword,
      }),
    );
  }
}
