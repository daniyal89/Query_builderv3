import { lazy, type ComponentType } from "react";
import { createRoutePreloader, registerRoutePreloader } from "./routePrefetch";

function createLazyPage(
  path: string,
  loader: () => Promise<{ default: ComponentType }>,
) {
  const preloader = createRoutePreloader(loader);
  registerRoutePreloader(path, preloader);
  return lazy(() => preloader() as Promise<{ default: ComponentType }>);
}

export const HomePage = createLazyPage("/", () =>
  import("../pages/HomePage").then((module) => ({ default: module.HomePage })),
);

export const QueryBuilderPage = createLazyPage("/query/local", () =>
  import("../pages/QueryBuilderPage").then((module) => ({ default: module.QueryBuilderPage })),
);

export const MarcadoseQueryBuilderPage = createLazyPage("/query/marcadose", () =>
  import("../pages/MarcadoseQueryBuilderPage").then((module) => ({
    default: module.MarcadoseQueryBuilderPage,
  })),
);

export const MergeEnrichPage = createLazyPage("/import", () =>
  import("../pages/MergeEnrichPage").then((module) => ({ default: module.MergeEnrichPage })),
);

export const FolderMergePage = createLazyPage("/folder-merge", () => import("../pages/FolderMergePage"));

export const FtpDownloadPage = createLazyPage("/ftp-download", () =>
  import("../pages/FtpDownloadPage").then((module) => ({ default: module.FtpDownloadPage })),
);

export const UploadMasterDrivePage = createLazyPage("/drive-upload-master", () =>
  import("../pages/UploadMasterDrivePage").then((module) => ({
    default: module.UploadMasterDrivePage,
  })),
);

export const DriveDownloadPage = createLazyPage("/drive-download", () =>
  import("../pages/DriveDownloadPage").then((module) => ({ default: module.DriveDownloadPage })),
);

export const SidebarToolsPage = createLazyPage("/sidebar-6-tools", () =>
  import("../pages/SidebarToolsPage").then((module) => ({ default: module.SidebarToolsPage })),
);
