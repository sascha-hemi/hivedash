import { Component, OnInit, inject } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { TranslatePipe } from '@ngx-translate/core';

import { SearchEngineService } from './search-engine.service';

/** The dashboard page's search bar - a launcher to an external search engine (Google/Bing/...),
 * not a search *within* HiveDash's own tiles. Engine choice persists to the account (see
 * SearchEngineService), exactly like the language switcher persists locale. */
@Component({
  selector: 'app-search-bar',
  imports: [FormsModule, TranslatePipe],
  templateUrl: './search-bar.html',
})
export class SearchBar implements OnInit {
  protected readonly engineService = inject(SearchEngineService);

  query = '';

  async ngOnInit(): Promise<void> {
    await this.engineService.ensureLoaded();
  }

  async onEngineChange(key: string): Promise<void> {
    await this.engineService.setEngine(key);
  }

  submit(): void {
    const url = this.engineService.buildUrl(this.query, this.engineService.effectiveEngine());
    if (url) {
      window.location.href = url;
    }
  }
}
