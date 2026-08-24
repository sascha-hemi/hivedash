import { Component, OnInit, ViewEncapsulation, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { TranslatePipe } from '@ngx-translate/core';

import { VersionService } from '../../core/version.service';
import { renderChangelogMarkdown } from './changelog-markdown';

/** Reachable from the account page - just renders CHANGELOG.md (GET /api/changelog). Angular's
 * default [innerHTML] sanitizer is left to do its job as-is; renderChangelogMarkdown() only ever
 * emits a small fixed set of safe tags (h1-h4/ul/li/p/strong/code/a), so there's nothing here
 * that needs bypassing. */
@Component({
  selector: 'app-changelog',
  imports: [TranslatePipe, RouterLink],
  templateUrl: './changelog.html',
  // The rendered changelog HTML is inserted via [innerHTML], so its elements never carry
  // Angular's emulated-encapsulation attribute and plain scoped styles below would never match
  // them. Turning encapsulation off is safe here since every selector is prefixed with the
  // page-local `.markdown` class, which no other component uses.
  encapsulation: ViewEncapsulation.None,
  styles: [`
    .markdown h2 { margin-top: 1.5rem; }
    .markdown h2:first-child { margin-top: 0; }
    .markdown h3 { margin-top: 1rem; font-size: 1rem; }
    .markdown ul { padding-left: 1.25rem; }
    .markdown p { margin-bottom: 0.5rem; }
  `],
})
export class ChangelogPage implements OnInit {
  private readonly versionService = inject(VersionService);

  readonly html = signal('');
  readonly loading = signal(true);

  async ngOnInit(): Promise<void> {
    try {
      const markdown = await this.versionService.fetchChangelog();
      this.html.set(renderChangelogMarkdown(markdown));
    } finally {
      this.loading.set(false);
    }
  }
}
