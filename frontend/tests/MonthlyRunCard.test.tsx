import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { rest } from "msw";
import { MonthlyRunCard } from "../src/components/sidebar/MonthlyRunCard";
import { server } from "./testServer";
import { renderWithAppContext } from "./testUtils";

const config = {
  ftp_host: "ftp.uppclonline.com",
  ftp_port: 21,
  ftp_remote_template: "/01-MASTER_DATA/{MON}_{YYYY}/",
  discoms: ["MVVNL", "DVVNL", "PVVNL", "PuVNL", "KESCO"],
  csv_root: "G:/MASTER",
  parquet_root: "G:/MASTER_PARQUET",
  db_path: "G:/MASTER/uppcl_latest.duckdb",
  object_type: "VIEW",
  compression: "snappy",
  drive_parent_folder_id: "parent",
  drive_root_name_template: "MASTER_DATA_{YYYY}_{MM}",
  drive_max_workers: 3,
  ftp_max_workers: 3,
  master_source: "ftp",
  drive_enable_emergency_proxy: false,
  drive_emergency_proxy_host: null,
  drive_emergency_proxy_port: null,
};

const step = (status: string, message = "") => ({ status, message, job_id: null, detail: {}, started_at: null, finished_at: null });

describe("MonthlyRunCard", () => {
  it("starts a run for the chosen month and shows each step finishing", async () => {
    const started: unknown[] = [];
    let polls = 0;

    server.use(
      rest.get("*/api/automation/config", (_req, res, ctx) => res(ctx.json(config))),
      rest.get("*/api/automation/monthly-run/active", (_req, res, ctx) => res(ctx.json(null))),
      rest.get("*/api/automation/monthly-run/plan", (req, res, ctx) =>
        res(
          ctx.json({
            default_month: "2026-07",
            month: req.url.searchParams.get("month"),
            token: "JUL_2026",
            object_name: "Master_0726",
            remote_dir: "/01-MASTER_DATA/JUL_2026/",
            csv_dir: "G:/MASTER/JUL_2026",
            csv_glob: "G:/MASTER/JUL_2026/**/*.gz",
            parquet_dir: "G:/MASTER_PARQUET/JUL_2026",
            drive_root_name: "MASTER_DATA_2026_07",
          }),
        ),
      ),
      rest.get("*/api/automation/monthly-run/marker", (_req, res, ctx) => res(ctx.json({ month: "JUL_2026", exists: false, steps: {} }))),
      rest.post("*/api/automation/monthly-run/start", async (req, res, ctx) => {
        started.push(await req.json());
        return res(ctx.json({ job_id: "job-1", status: "queued", message: "Monthly run for JUL_2026 queued.", month: "JUL_2026", object_name: "Master_0726" }));
      }),
      rest.get("*/api/automation/monthly-run/status/job-1", (_req, res, ctx) => {
        polls += 1;
        const done = polls > 1;
        return res(
          ctx.json({
            job_id: "job-1",
            status: done ? "completed" : "running",
            message: done ? "JUL_2026 is downloaded, uploaded to Drive and available as Master_0726." : "Working…",
            month: "JUL_2026",
            object_name: "Master_0726",
            outcome: done ? "completed" : null,
            current_step: done ? null : "download",
            steps: {
              download: step(done ? "completed" : "running", "Checking the FTP server..."),
              upload: step(done ? "completed" : "pending"),
              build: step(done ? "completed" : "pending"),
            },
            resumed_steps: [],
            missing_discoms: [],
            paths: {},
          }),
        );
      }),
    );

    const user = userEvent.setup();
    renderWithAppContext(<MonthlyRunCard />, { route: "/sidebar-tools" });

    expect(await screen.findByText("Master_0726")).toBeInTheDocument();

    await user.click(await screen.findByRole("button", { name: /run monthly master/i }));

    await waitFor(() => expect(started).toHaveLength(1));
    expect(started[0]).toMatchObject({ from_scratch: false });
    expect(String((started[0] as { month: string }).month)).toMatch(/^\d{4}-\d{2}$/);

    expect(await screen.findByText(/available as Master_0726/i, {}, { timeout: 8000 })).toBeInTheDocument();
    expect(screen.getAllByText("completed")).toHaveLength(3);
  }, 15000);

  it("choosing Google Drive remembers it for this computer, runs with it and skips the upload", async () => {
    const started: unknown[] = [];
    const savedConfigs: unknown[] = [];

    server.use(
      rest.get("*/api/automation/config", (_req, res, ctx) => res(ctx.json(config))),
      rest.put("*/api/automation/config", async (req, res, ctx) => {
        const body = await req.json();
        savedConfigs.push(body);
        return res(ctx.json(body));
      }),
      rest.get("*/api/automation/monthly-run/active", (_req, res, ctx) => res(ctx.json(null))),
      rest.get("*/api/automation/monthly-run/plan", (_req, res, ctx) =>
        res(ctx.json({ default_month: "2026-07", month: "2026-07", token: "JUL_2026", object_name: "Master_0726", remote_dir: "/01-MASTER_DATA/JUL_2026/", csv_dir: "", csv_glob: "", parquet_dir: "", drive_root_name: "MASTER_DATA_2026_07" })),
      ),
      rest.get("*/api/automation/monthly-run/marker", (_req, res, ctx) => res(ctx.json({ month: "JUL_2026", exists: false, steps: {} }))),
      rest.post("*/api/automation/monthly-run/start", async (req, res, ctx) => {
        started.push(await req.json());
        return res(ctx.json({ job_id: "job-2", status: "queued", message: "queued", month: "JUL_2026", object_name: "Master_0726" }));
      }),
      rest.get("*/api/automation/monthly-run/status/job-2", (_req, res, ctx) =>
        res(
          ctx.json({
            job_id: "job-2",
            status: "completed",
            message: "JUL_2026 is downloaded from Drive and available as Master_0726.",
            month: "JUL_2026",
            object_name: "Master_0726",
            outcome: "completed",
            source: "drive",
            current_step: null,
            steps: {
              download: step("completed", "Downloaded 50 file(s) from Drive across 5 DISCOM(s)."),
              upload: step("skipped", "The month is taken from Google Drive, so there is nothing to upload."),
              build: step("completed"),
            },
            resumed_steps: [],
            missing_discoms: [],
            paths: {},
          }),
        ),
      ),
    );

    const user = userEvent.setup();
    renderWithAppContext(<MonthlyRunCard />, { route: "/sidebar-tools" });
    expect(await screen.findByText("Master_0726")).toBeInTheDocument();

    await user.click(screen.getByRole("radio", { name: /google drive/i }));
    await user.click(await screen.findByRole("button", { name: /run monthly master/i }));

    await waitFor(() => expect(started).toHaveLength(1));
    expect(started[0]).toMatchObject({ source: "drive" });
    expect(savedConfigs).toHaveLength(1);
    expect(savedConfigs[0]).toMatchObject({ master_source: "drive" }, );

    expect(await screen.findByText(/downloaded from Drive and available/i, {}, { timeout: 8000 })).toBeInTheDocument();
    expect(screen.getByText("1 · Download from Google Drive")).toBeInTheDocument();
    expect(screen.getByText("skipped")).toBeInTheDocument();
    expect(screen.getByText(/nothing to upload/i)).toBeInTheDocument();
  }, 15000);

  it("recovers once the backend comes up instead of staying dead", async () => {
    // The page is often opened before the server has finished starting. The
    // first settings fetch fails; the card must not need a page reload.
    let configCalls = 0;
    server.use(
      rest.get("*/api/automation/config", (_req, res, ctx) => {
        configCalls += 1;
        return configCalls === 1 ? res.networkError("backend not up yet") : res(ctx.json(config));
      }),
      rest.get("*/api/automation/monthly-run/active", (_req, res, ctx) => res(ctx.json(null))),
      rest.get("*/api/automation/monthly-run/plan", (_req, res, ctx) =>
        res(ctx.json({ default_month: "2026-09", month: "2026-09", token: "SEP_2026", object_name: "Master_0926", remote_dir: "", csv_dir: "", csv_glob: "", parquet_dir: "", drive_root_name: "" })),
      ),
      rest.get("*/api/automation/monthly-run/marker", (_req, res, ctx) => res(ctx.json({ month: "SEP_2026", exists: false, steps: {} }))),
    );

    const user = userEvent.setup();
    renderWithAppContext(<MonthlyRunCard />, { route: "/sidebar-tools" });

    expect(await screen.findByText(/is the backend running/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /run monthly master/i })).toBeDisabled();

    await user.click(screen.getByRole("button", { name: /retry now/i }));

    await waitFor(() => expect(screen.getByRole("button", { name: /run monthly master/i })).toBeEnabled());
    expect(screen.queryByText(/is the backend running/i)).not.toBeInTheDocument();
    expect(configCalls).toBe(2);
  });

  it("offers to resume when the month already has completed steps", async () => {
    server.use(
      rest.get("*/api/automation/config", (_req, res, ctx) => res(ctx.json(config))),
      rest.get("*/api/automation/monthly-run/active", (_req, res, ctx) => res(ctx.json(null))),
      rest.get("*/api/automation/monthly-run/plan", (_req, res, ctx) =>
        res(ctx.json({ default_month: "2026-07", month: "2026-07", token: "JUL_2026", object_name: "Master_0726", remote_dir: "", csv_dir: "", csv_glob: "", parquet_dir: "", drive_root_name: "" })),
      ),
      rest.get("*/api/automation/monthly-run/marker", (_req, res, ctx) =>
        res(ctx.json({ month: "JUL_2026", exists: true, steps: { download: step("completed", "Downloaded 615 file(s)"), upload: step("completed") } })),
      ),
    );

    renderWithAppContext(<MonthlyRunCard />, { route: "/sidebar-tools" });

    expect(await screen.findByRole("button", { name: /resume \(2 of 3 done\)/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /run again from scratch/i })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^run monthly master$/i })).not.toBeInTheDocument();
  });
});
