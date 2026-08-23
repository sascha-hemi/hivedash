import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { firstValueFrom } from 'rxjs';

import {
  AdminDashboard,
  AdminDashboardItem,
  AdminUser,
  AvailableService,
  CatalogIconResult,
  Category,
  CustomService,
  DiscoveredService,
  Logo,
  TileSize,
} from './models';

@Injectable({ providedIn: 'root' })
export class AdminService {
  private readonly http = inject(HttpClient);

  listUsers(): Promise<AdminUser[]> {
    return firstValueFrom(this.http.get<AdminUser[]>('/api/admin/users'));
  }

  createUser(payload: {
    email: string;
    password?: string | null;
    display_name?: string | null;
    role?: string;
    dashboard_id?: number | null;
  }): Promise<AdminUser> {
    return firstValueFrom(this.http.post<AdminUser>('/api/admin/users', payload));
  }

  updateUser(
    id: number,
    payload: Partial<{
      email: string;
      password: string;
      display_name: string | null;
      role: string;
      dashboard_id: number | null;
      is_active: boolean;
    }>,
  ): Promise<AdminUser> {
    return firstValueFrom(this.http.patch<AdminUser>(`/api/admin/users/${id}`, payload));
  }

  deleteUser(id: number): Promise<{ status: string }> {
    return firstValueFrom(this.http.delete<{ status: string }>(`/api/admin/users/${id}`));
  }

  listDashboards(): Promise<AdminDashboard[]> {
    return firstValueFrom(this.http.get<AdminDashboard[]>('/api/admin/dashboards'));
  }

  createDashboard(name: string, cloneFromId: number | null = null): Promise<AdminDashboard> {
    return firstValueFrom(
      this.http.post<AdminDashboard>('/api/admin/dashboards', {
        name,
        clone_from_id: cloneFromId,
      }),
    );
  }

  renameDashboard(id: number, name: string): Promise<AdminDashboard> {
    return firstValueFrom(
      this.http.patch<AdminDashboard>(`/api/admin/dashboards/${id}`, { name }),
    );
  }

  setDefaultDashboard(id: number): Promise<AdminDashboard> {
    return firstValueFrom(
      this.http.patch<AdminDashboard>(`/api/admin/dashboards/${id}`, { is_default: true }),
    );
  }

  setTileSize(id: number, tileSize: TileSize): Promise<AdminDashboard> {
    return firstValueFrom(
      this.http.patch<AdminDashboard>(`/api/admin/dashboards/${id}`, { tile_size: tileSize }),
    );
  }

  deleteDashboard(id: number): Promise<{ status: string }> {
    return firstValueFrom(
      this.http.delete<{ status: string }>(`/api/admin/dashboards/${id}`),
    );
  }

  listDashboardItems(dashboardId: number): Promise<AdminDashboardItem[]> {
    return firstValueFrom(
      this.http.get<AdminDashboardItem[]>(`/api/admin/dashboards/${dashboardId}/items`),
    );
  }

  updateDashboardItems(
    dashboardId: number,
    updates: Array<{
      item_id: number;
      visible?: boolean;
      sort_order?: number;
      category_id?: number | null;
    }>,
  ): Promise<AdminDashboardItem[]> {
    return firstValueFrom(
      this.http.patch<AdminDashboardItem[]>(
        `/api/admin/dashboards/${dashboardId}/items`,
        updates,
      ),
    );
  }

  attachService(
    dashboardId: number,
    kind: 'proxy_host' | 'guest' | 'custom_service',
    id: number,
  ): Promise<{ item_id: number }> {
    return firstValueFrom(
      this.http.post<{ item_id: number }>(`/api/admin/dashboards/${dashboardId}/items`, {
        kind,
        id,
      }),
    );
  }

  listAvailableServices(): Promise<AvailableService[]> {
    return firstValueFrom(this.http.get<AvailableService[]>('/api/admin/services'));
  }

  listDiscoveredServices(): Promise<DiscoveredService[]> {
    return firstValueFrom(this.http.get<DiscoveredService[]>('/api/admin/services/discovered'));
  }

  updateService(
    kind: 'proxy_host' | 'guest',
    serviceId: number,
    payload: Partial<{ logo_id: number | null; custom_name: string | null; custom_url: string | null }>,
  ): Promise<{ status: string }> {
    return firstValueFrom(
      this.http.patch<{ status: string }>(`/api/admin/services/${kind}/${serviceId}`, payload),
    );
  }

  listCustomServices(): Promise<CustomService[]> {
    return firstValueFrom(this.http.get<CustomService[]>('/api/admin/custom-services'));
  }

  createCustomService(payload: {
    name: string;
    url?: string | null;
    logo_id?: number | null;
  }): Promise<CustomService> {
    return firstValueFrom(this.http.post<CustomService>('/api/admin/custom-services', payload));
  }

  updateCustomService(
    id: number,
    payload: Partial<{ name: string; url: string | null; logo_id: number | null }>,
  ): Promise<CustomService> {
    return firstValueFrom(
      this.http.patch<CustomService>(`/api/admin/custom-services/${id}`, payload),
    );
  }

  deleteCustomService(id: number): Promise<{ status: string }> {
    return firstValueFrom(
      this.http.delete<{ status: string }>(`/api/admin/custom-services/${id}`),
    );
  }

  listLogos(): Promise<Logo[]> {
    return firstValueFrom(this.http.get<Logo[]>('/api/admin/logos'));
  }

  uploadLogo(name: string, keywords: string, file: File): Promise<Logo> {
    const formData = new FormData();
    formData.append('name', name);
    formData.append('keywords', keywords);
    formData.append('file', file);
    return firstValueFrom(this.http.post<Logo>('/api/admin/logos', formData));
  }

  deleteLogo(id: number): Promise<{ status: string }> {
    return firstValueFrom(this.http.delete<{ status: string }>(`/api/admin/logos/${id}`));
  }

  searchLogoCatalog(query: string): Promise<CatalogIconResult[]> {
    const params = new URLSearchParams({ q: query });
    return firstValueFrom(
      this.http.get<CatalogIconResult[]>(`/api/admin/logos/catalog/search?${params}`),
    );
  }

  importLogoFromCatalog(slug: string): Promise<Logo> {
    return firstValueFrom(
      this.http.post<Logo>('/api/admin/logos/catalog/import', { slug }),
    );
  }

  listCategories(dashboardId: number): Promise<Category[]> {
    return firstValueFrom(
      this.http.get<Category[]>(`/api/admin/dashboards/${dashboardId}/categories`),
    );
  }

  createCategory(dashboardId: number, name: string): Promise<Category> {
    return firstValueFrom(
      this.http.post<Category>(`/api/admin/dashboards/${dashboardId}/categories`, { name }),
    );
  }

  updateCategory(
    dashboardId: number,
    categoryId: number,
    payload: Partial<{ name: string; sort_order: number }>,
  ): Promise<Category> {
    return firstValueFrom(
      this.http.patch<Category>(
        `/api/admin/dashboards/${dashboardId}/categories/${categoryId}`,
        payload,
      ),
    );
  }

  deleteCategory(dashboardId: number, categoryId: number): Promise<{ status: string }> {
    return firstValueFrom(
      this.http.delete<{ status: string }>(
        `/api/admin/dashboards/${dashboardId}/categories/${categoryId}`,
      ),
    );
  }
}
