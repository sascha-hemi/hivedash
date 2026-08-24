import { Injectable, signal } from '@angular/core';

export type ToastVariant = 'danger' | 'warning' | 'success';

export interface Toast {
  id: number;
  message: string;
  variant: ToastVariant;
}

const AUTO_DISMISS_MS = 6000;

/** App-wide toast notifications (Tabler/Bootstrap toast markup, see toast-container.html) -
 * replaces the old per-page inline `<div class="alert">` error banners. Deliberately NOT built
 * on Bootstrap's own `bootstrap.Toast` JS class (which the bundled tabler.min.js does ship) -
 * show/hide/auto-dismiss is driven entirely by this service's own signal + timer instead, so a
 * toast's lifecycle has exactly one owner (this service) rather than being split between
 * Angular's view and Bootstrap's imperative DOM manipulation. Still uses Tabler's exact toast
 * CSS classes, so it looks identical to a "real" Tabler toast. */
@Injectable({ providedIn: 'root' })
export class ToastService {
  private nextId = 0;
  readonly toasts = signal<Toast[]>([]);

  show(message: string, variant: ToastVariant = 'danger'): void {
    const id = this.nextId++;
    this.toasts.update((list) => [...list, { id, message, variant }]);
    setTimeout(() => this.dismiss(id), AUTO_DISMISS_MS);
  }

  dismiss(id: number): void {
    this.toasts.update((list) => list.filter((t) => t.id !== id));
  }
}
