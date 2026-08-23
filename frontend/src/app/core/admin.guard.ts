import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';

import { AuthService } from './auth.service';

export const adminGuard: CanActivateFn = async () => {
  const auth = inject(AuthService);
  const router = inject(Router);

  if (!auth.checked()) {
    await auth.fetchMe();
  }
  if (auth.isAdmin()) {
    return true;
  }
  return router.createUrlTree(auth.user() ? ['/'] : ['/login']);
};
