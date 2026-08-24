import { HttpClient } from '@angular/common/http';
import { Injectable, computed, inject, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';

import { AuthConfig, CurrentUser, SearchEngine } from '../core/models';
import { AuthService } from '../core/auth.service';

/** Backs the dashboard's search bar. Unlike locales, the engine catalog isn't known at compile
 * time - it comes from GET /api/auth/config (SEARCH_ENGINES in app/search_engines.py), so
 * `ensureLoaded()` has to run once before the search bar can render its engine picker. Engine
 * choice follows the exact same "account override, else instance default" idiom as
 * LocaleService: a signed-in user's own `search_engine` (once set) always wins over the
 * instance's SEARCH_ENGINE default, persisted via the same self-service PATCH /api/auth/me. */
@Injectable({ providedIn: 'root' })
export class SearchEngineService {
  private readonly http = inject(HttpClient);
  private readonly auth = inject(AuthService);

  private readonly loaded = signal(false);
  readonly engines = signal<Record<string, SearchEngine>>({});
  readonly defaultEngine = signal('google');

  readonly engineKeys = computed(() => Object.keys(this.engines()));

  readonly effectiveEngine = computed(() => {
    const chosen = this.auth.user()?.search_engine;
    return chosen && this.engines()[chosen] ? chosen : this.defaultEngine();
  });

  async ensureLoaded(): Promise<void> {
    if (this.loaded()) return;
    try {
      const config = await firstValueFrom(this.http.get<AuthConfig>('/api/auth/config'));
      this.engines.set(config.search_engines);
      this.defaultEngine.set(config.default_search_engine);
      this.loaded.set(true);
    } catch {
      // best-effort - the search bar just stays hidden/empty for this load if the config
      // request fails; not worth surfacing an error banner for.
    }
  }

  async setEngine(key: string | null): Promise<void> {
    if (!this.auth.user()) return;
    const updated = await firstValueFrom(
      this.http.patch<CurrentUser>('/api/auth/me', { search_engine: key }),
    );
    this.auth.setUserSearchEngine(updated.search_engine);
  }

  /** Returns null for an empty query or an unknown engine key - callers should no-op rather
   * than navigate to a broken/empty search. */
  buildUrl(query: string, engineKey: string): string | null {
    const trimmed = query.trim();
    const engine = this.engines()[engineKey];
    if (!trimmed || !engine) return null;
    return engine.url_template.replace('{query}', encodeURIComponent(trimmed));
  }
}
