import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { firstValueFrom } from 'rxjs';

import { VersionInfo } from './models';

@Injectable({ providedIn: 'root' })
export class VersionService {
  private readonly http = inject(HttpClient);

  fetch(): Promise<VersionInfo> {
    return firstValueFrom(this.http.get<VersionInfo>('/api/version'));
  }

  fetchChangelog(): Promise<string> {
    return firstValueFrom(this.http.get<{ markdown: string }>('/api/changelog')).then(
      (r) => r.markdown,
    );
  }
}
