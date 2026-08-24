import { Component, OnInit, inject } from '@angular/core';
import { Router, RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { TranslatePipe } from '@ngx-translate/core';

import { AuthService } from './core/auth.service';
import { ToastContainer } from './core/toast-container';
import { LocaleService } from './i18n/locale.service';

@Component({
  selector: 'app-root',
  imports: [RouterOutlet, RouterLink, RouterLinkActive, TranslatePipe, ToastContainer],
  templateUrl: './app.html',
  styleUrl: './app.scss',
})
export class App implements OnInit {
  protected readonly auth = inject(AuthService);
  private readonly router = inject(Router);
  // Constructing this here (rather than only where it's first used deep in some page) makes
  // sure the browser-detected/cached language is applied before anything - including the
  // pre-login pages - ever renders.
  private readonly locale = inject(LocaleService);

  async ngOnInit(): Promise<void> {
    await this.auth.fetchMe();
  }

  async logout(): Promise<void> {
    await this.auth.logout();
    await this.router.navigateByUrl('/login');
  }
}
