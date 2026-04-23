import apiClient from "./client";

interface PickPathResponse {
  path: string | null;
}

export async function pickSystemFolder(): Promise<string | null> {
  const response = await apiClient.get<PickPathResponse>("/system/pick-folder");
  return response.data.path;
}
