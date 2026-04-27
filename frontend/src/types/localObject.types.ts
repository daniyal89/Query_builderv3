import type { TableMetadata } from "./schema.types";

export type LocalFileObjectType = "TABLE" | "VIEW";

export interface FileObjectRequest {
  file_path: string;
  object_name: string;
  object_type: LocalFileObjectType;
  replace: boolean;
  header: boolean;
  sheet_name?: string | null;
  header_names?: string[];
}

export interface FileObjectResponse {
  status: string;
  message: string;
  object_name: string;
  object_type: LocalFileObjectType;
  table: TableMetadata;
}

export interface FilePreviewRequest {
  file_path: string;
  header: boolean;
  sheet_name?: string | null;
  limit_rows?: number;
}

export interface FilePreviewResponse {
  columns: string[];
  rows: Array<Array<string | number | null>>;
}
