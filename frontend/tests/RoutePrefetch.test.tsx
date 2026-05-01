import { afterEach, describe, expect, it, vi } from "vitest";
import {
  __unsafeResetRoutePreloaders,
  createRoutePreloader,
  prefetchRoute,
  registerRoutePreloader,
  scheduleRoutePrefetch,
} from "../src/app/routePrefetch";

describe("routePrefetch", () => {
  afterEach(() => {
    __unsafeResetRoutePreloaders();
    vi.useRealTimers();
  });

  it("reuses the same pending preload promise for repeated requests", async () => {
    const loader = vi.fn(async () => ({ default: () => null }));
    registerRoutePreloader("/query/local", createRoutePreloader(loader));

    await Promise.all([
      prefetchRoute("/query/local"),
      prefetchRoute("/query/local"),
      prefetchRoute("/query/local"),
    ]);

    expect(loader).toHaveBeenCalledTimes(1);
  });

  it("schedules idle route prefetch with the timeout fallback when requestIdleCallback is unavailable", () => {
    vi.useFakeTimers();
    const loader = vi.fn(async () => ({ default: () => null }));
    registerRoutePreloader("/import", createRoutePreloader(loader));

    const cancel = scheduleRoutePrefetch(["/import", "/import"]);
    expect(loader).not.toHaveBeenCalled();

    vi.advanceTimersByTime(150);

    expect(loader).toHaveBeenCalledTimes(1);
    cancel();
  });
});
