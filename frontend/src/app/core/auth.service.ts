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
}
