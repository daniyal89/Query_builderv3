/**
 * client.ts — Pre-configured Axios instance for all backend API calls.
 *
 * Sets baseURL to /api so all calls are relative, and attaches a global
 * error interceptor for consistent error handling across the app.
 */

import axios from "axios";

/** Axios instance pre-configured for the dashboard API. */
const apiClient = axios.create({
  baseURL: "/api",
  timeout: 30_000,
  headers: {
    "Content-Type": "application/json",
  },
});

apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    const detail =
      error?.response?.data?.detail ||
      error?.response?.data?.error ||
      error?.message ||
      "Request failed.";

    error.normalizedMessage = typeof detail === "string" ? detail : JSON.stringify(detail);
    error.requestId = error?.response?.headers?.["x-request-id"] ?? null;
    return Promise.reject(error);
  },
);

export default apiClient;
