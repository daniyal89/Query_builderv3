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

// TODO: Attach response interceptor for global error handling

export default apiClient;
