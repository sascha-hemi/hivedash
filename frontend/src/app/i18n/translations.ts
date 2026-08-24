/** Shape every language file must implement - keeps en.ts (the fallback) as the single source of
 * truth for which keys exist, so a missing translation in another language is a type error, not a
 * silent blank string discovered at runtime. */
export interface Translations {
  nav: {
    settings: string;
    logout: string;
    account: string;
  };
  login: {
    title: string;
    email: string;
    password: string;
    or: string;
    ssoButton: string;
    invalidCredentials: string;
  };
  dashboard: {
    updated: string;
    noDataYet: string;
    reconnecting: string;
    edit: string;
    done: string;
    saving: string;
    services: string;
    infrastructure: string;
    dragTilesHere: string;
    noEntries: string;
    drag: string;
    newCategory: string;
    deleteCategoryConfirm: string;
    apiUnreachable: string;
    saveFailedReload: string;
    renameFailed: string;
    deleteFailed: string;
    createFailed: string;
    moveFailed: string;
  };
  tile: {
    cpu: string;
    ram: string;
    vmOnNode: string;
    statusUnknown: string;
    online: string;
    offline: string;
  };
  admin: {
    shell: {
      title: string;
      services: string;
      dashboards: string;
      logos: string;
      users: string;
    };
    services: {
      autoDetected: string;
      autoDetectedHint: string;
      type: string;
      recognizedAs: string;
      logo: string;
      customName: string;
      customUrl: string;
      noLogo: string;
      asRecognizedPlaceholder: string;
      noneDetectedYet: string;
      newCustomService: string;
      name: string;
      url: string;
      namePlaceholder: string;
      ownServices: string;
      ownServicesHint: string;
      noneCreatedYet: string;
      npmBadge: string;
      proxmoxBadge: string;
      combinedBadge: string;
      confirmDeleteCustom: string;
      renameFailed: string;
      urlSaveFailed: string;
      logoAssignFailed: string;
      createFailed: string;
      deleteFailed: string;
    };
    dashboards: {
      newDashboard: string;
      startsAsCopy: string;
      name: string;
      namePlaceholder: string;
      create: string;
      colName: string;
      colDefault: string;
      setAsDefault: string;
      confirmDelete: string;
      createFailed: string;
      deleteFailed: string;
    };
    dashboardEdit: {
      settings: string;
      save: string;
      tileSize: string;
      small: string;
      medium: string;
      large: string;
      addService: string;
      type: string;
      npmHost: string;
      proxmoxGuest: string;
      customService: string;
      service: string;
      choose: string;
      add: string;
      orderVisibility: string;
      configuredElsewhere: string;
      saving: string;
      noCategory: string;
      visible: string;
      noneYet: string;
      renameFailed: string;
      tileSizeFailed: string;
      addFailed: string;
      categoryAssignFailed: string;
    };
    logos: {
      importFromCatalog: string;
      searchHint: string;
      searchPlaceholder: string;
      noResults: string;
      import: string;
      uploadOwn: string;
      name: string;
      keywords: string;
      keywordsHint: string;
      imageFile: string;
      upload: string;
      library: string;
      colKeywords: string;
      noneYet: string;
      confirmDelete: string;
      uploadFailed: string;
      deleteFailed: string;
      searchFailed: string;
      importFailed: string;
    };
    users: {
      createNew: string;
      email: string;
      password: string;
      localOnly: string;
      name: string;
      role: string;
      user: string;
      admin: string;
      dashboard: string;
      default: string;
      create: string;
      colEmail: string;
      colName: string;
      colRole: string;
      colDashboard: string;
      colStatus: string;
      active: string;
      locked: string;
      confirmDelete: string;
      createFailed: string;
      actionFailed: string;
      deleteFailed: string;
    };
  };
  language: {
    label: string;
    auto: string;
  };
  account: {
    title: string;
    languageTitle: string;
    passwordTitle: string;
    currentPassword: string;
    newPassword: string;
    confirmPassword: string;
    save: string;
    passwordMismatch: string;
    passwordEmpty: string;
    passwordChanged: string;
    changeFailed: string;
    ssoManaged: string;
  };
}
