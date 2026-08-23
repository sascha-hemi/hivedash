import { NgTemplateOutlet } from '@angular/common';
import { Component, Input } from '@angular/core';

import { avatarColorClass, formatBytes, initials, kindLabel, statusDotClass, statusDotTitle } from '../../core/format';
import { ServiceTile } from '../../core/models';

@Component({
  selector: 'app-service-card',
  imports: [NgTemplateOutlet],
  templateUrl: './service-card.html',
})
export class ServiceCard {
  @Input({ required: true }) tile!: ServiceTile;

  get dotClass(): string {
    return statusDotClass(this.tile.online);
  }

  get dotTitle(): string {
    return statusDotTitle(this.tile.online);
  }

  get subLine(): string {
    if (this.tile.vm) {
      return `${this.tile.vm.node} · ${kindLabel(this.tile.vm.kind)} #${this.tile.vm.vmid}`;
    }
    if (this.tile.forward_host) {
      return `→ ${this.tile.forward_host}:${this.tile.forward_port}`;
    }
    return '';
  }

  get cpuPercent(): string | null {
    return this.tile.vm?.cpu != null ? (this.tile.vm.cpu * 100).toFixed(0) : null;
  }

  get memLabel(): string | null {
    if (this.tile.vm?.mem == null || !this.tile.vm.maxmem) return null;
    return `${formatBytes(this.tile.vm.mem)} / ${formatBytes(this.tile.vm.maxmem)}`;
  }

  get avatarColorClass(): string {
    return avatarColorClass(this.tile.name);
  }

  get initials(): string {
    return initials(this.tile.name);
  }
}
