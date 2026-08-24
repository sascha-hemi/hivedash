import { Component, inject } from '@angular/core';
import { TranslatePipe } from '@ngx-translate/core';

import { ToastService } from './toast.service';

/** Mounted once in app.html (outside the logged-in-only navbar block, so it also works on the
 * pre-login pages) - every page just injects ToastService and calls .show(), this renders
 * whatever's currently queued. */
@Component({
  selector: 'app-toast-container',
  imports: [TranslatePipe],
  templateUrl: './toast-container.html',
})
export class ToastContainer {
  protected readonly toastService = inject(ToastService);

  dismiss(id: number): void {
    this.toastService.dismiss(id);
  }
}
