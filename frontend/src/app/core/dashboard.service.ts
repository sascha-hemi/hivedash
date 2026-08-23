import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { firstValueFrom } from 'rxjs';

import { DashboardResponse } from './models';

@Injectable({ providedIn: 'root' })
export class DashboardService {
  private readonly http = inject(HttpClient);

  fetch(): Promise<DashboardResponse> {
    return firstValueFrom(this.http.get<DashboardResponse>('/api/dashboard'));
  }
}
