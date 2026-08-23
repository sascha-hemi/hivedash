import { NgTemplateOutlet } from '@angular/common';
import { Component, Input } from '@angular/core';

import { avatarColorClass, initials } from '../../core/format';
import { CustomTile } from '../../core/models';

@Component({
  selector: 'app-custom-card',
  imports: [NgTemplateOutlet],
  templateUrl: './custom-card.html',
})
export class CustomCard {
  @Input({ required: true }) tile!: CustomTile;

  get avatarColorClass(): string {
    return avatarColorClass(this.tile.name);
  }

  get initials(): string {
    return initials(this.tile.name);
  }
}
