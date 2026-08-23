import { NgTemplateOutlet } from '@angular/common';
import { Component, Input } from '@angular/core';

import { avatarColorClass, formatBytes, initials, kindLabel, statusDotClass } from '../../core/format';
import { InfrastructureTile } from '../../core/models';

@Component({
  selector: 'app-infra-card',
  imports: [NgTemplateOutlet],
  templateUrl: './infra-card.html',
})
export class InfraCard {
  @Input({ required: true }) tile!: InfrastructureTile;

  get dotClass(): string {
    return statusDotClass(this.tile.status);
  }

  get firstIp(): string | null {
    return this.tile.ip_addresses?.length ? this.tile.ip_addresses[0] : null;
  }

  get cpuPercent(): string | null {
    return this.tile.cpu != null ? (this.tile.cpu * 100).toFixed(0) : null;
  }

  get memLabel(): string | null {
    if (this.tile.mem == null || !this.tile.maxmem) return null;
    return `${formatBytes(this.tile.mem)} / ${formatBytes(this.tile.maxmem)}`;
  }

  get avatarColorClass(): string {
    return avatarColorClass(this.tile.name);
  }

  get initials(): string {
    return initials(this.tile.name);
  }

  get kindLabel(): string {
    return kindLabel(this.tile.kind);
  }
}
