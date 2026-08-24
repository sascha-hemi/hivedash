import { Routes } from '@angular/router';

import { adminGuard } from './core/admin.guard';
import { authGuard } from './core/auth.guard';

export const routes: Routes = [
  {
    path: 'login',
    loadComponent: () => import('./pages/login/login').then((m) => m.LoginPage),
  },
  {
    path: '',
    canActivate: [authGuard],
    loadComponent: () => import('./pages/dashboard/dashboard').then((m) => m.DashboardPage),
  },
  {
    path: 'account',
    canActivate: [authGuard],
    loadComponent: () => import('./pages/account/account').then((m) => m.AccountPage),
  },
  {
    path: 'admin',
    canActivate: [adminGuard],
    loadComponent: () => import('./pages/admin/admin-shell').then((m) => m.AdminShell),
    children: [
      { path: '', pathMatch: 'full', redirectTo: 'services' },
      {
        path: 'users',
        loadComponent: () =>
          import('./pages/admin/users/admin-users').then((m) => m.AdminUsersPage),
      },
      {
        path: 'dashboards',
        loadComponent: () =>
          import('./pages/admin/dashboards/admin-dashboards').then(
            (m) => m.AdminDashboardsPage,
          ),
      },
      {
        path: 'dashboards/:id',
        loadComponent: () =>
          import('./pages/admin/dashboards/admin-dashboard-edit').then(
            (m) => m.AdminDashboardEditPage,
          ),
      },
      {
        path: 'logos',
        loadComponent: () =>
          import('./pages/admin/logos/admin-logos').then((m) => m.AdminLogosPage),
      },
      {
        path: 'services',
        loadComponent: () =>
          import('./pages/admin/services/admin-services').then((m) => m.AdminServicesPage),
      },
    ],
  },
  { path: '**', redirectTo: '' },
];
