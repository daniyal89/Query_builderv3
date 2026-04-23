import type { TableMetadata } from "./schema.types";

export type LocalFileObjectType = "TABLE" | "VIEW";

export interface FileObjectRequest {
  file_path: string;
  object_name: string;
  object_type: LocalFileObjectType;
  replace: boolean;
  header: boolean;
  sheet_name?: string | null;
}

export interface FileObjectResponse {
  status: string;
  message: string;
  object_name: string;
  object_type: LocalFileObjectType;
  table: TableMetadata;
}
