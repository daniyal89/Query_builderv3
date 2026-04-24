const SYSTEM_API_BASE = "/api/system";

type SystemPathResponse = {
  path?: string | null;
};

async function postForPath(
  endpoint: string,
  payload: Record<string, unknown> = {},
): Promise<string | null> {
  const response = await fetch(`${SYSTEM_API_BASE}${endpoint}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || `Request failed for ${endpoint}`);
  }

  const data = (await response.json()) as SystemPathResponse;
  return data.path ?? null;
}

export async function pickSystemFile(fileType?: "duckdb" | "data" | "json"): Promise<string | null> {
  return postForPath("/pick-file", {
    file_type: fileType ?? null,
  });
}

export async function pickSystemFolder(): Promise<string | null> {
  return postForPath("/pick-folder");
}

export async function pickSystemSavePath(
  defaultFileName = "merged_output.csv",
  extension = ".csv",
): Promise<string | null> {
  return postForPath("/pick-save-path", {
    default_file_name: defaultFileName,
    extension,
  });
}
