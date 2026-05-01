type RoutePreloader = () => Promise<unknown>;

const registeredRoutePreloaders = new Map<string, RoutePreloader>();
const IDLE_PREFETCH_DELAY_MS = 150;

function requestIdleWork(task: () => void): () => void {
  if (typeof window === "undefined") {
    task();
    return () => undefined;
  }

  if ("requestIdleCallback" in window && "cancelIdleCallback" in window) {
    const idleId = window.requestIdleCallback(() => task());
    return () => window.cancelIdleCallback(idleId);
  }

  const timeoutId = globalThis.setTimeout(task, IDLE_PREFETCH_DELAY_MS);
  return () => globalThis.clearTimeout(timeoutId);
}

export function createRoutePreloader(loader: RoutePreloader): RoutePreloader {
  let pending: Promise<unknown> | null = null;

  return () => {
    if (!pending) {
      pending = loader().catch((error) => {
        pending = null;
        throw error;
      });
    }
    return pending;
  };
}

export function registerRoutePreloader(path: string, preloader: RoutePreloader): void {
  registeredRoutePreloaders.set(path, preloader);
}

export function prefetchRoute(path: string): Promise<unknown> | undefined {
  return registeredRoutePreloaders.get(path)?.();
}

export function scheduleRoutePrefetch(paths: string[]): () => void {
  const uniquePaths = Array.from(new Set(paths));
  return requestIdleWork(() => {
    for (const path of uniquePaths) {
      void prefetchRoute(path);
    }
  });
}

export function __unsafeResetRoutePreloaders(): void {
  registeredRoutePreloaders.clear();
}
