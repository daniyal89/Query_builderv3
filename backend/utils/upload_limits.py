from __future__ import annotations

from fastapi import HTTPException, UploadFile, status


DEFAULT_UPLOAD_CHUNK_BYTES = 1024 * 1024


def enforce_total_upload_limit(total_bytes: int, max_bytes: int, label: str) -> None:
    if total_bytes > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"{label} exceeds the maximum allowed size of {max_bytes} bytes.",
        )


async def read_upload_bytes(
    upload: UploadFile,
    *,
    max_bytes: int,
    label: str,
    chunk_bytes: int = DEFAULT_UPLOAD_CHUNK_BYTES,
) -> bytes:
    total_bytes = 0
    chunks: list[bytes] = []

    while True:
        chunk = await upload.read(chunk_bytes)
        if not chunk:
            break
        total_bytes += len(chunk)
        if total_bytes > max_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail=f"{label} exceeds the maximum allowed size of {max_bytes} bytes.",
            )
        chunks.append(chunk)

    return b"".join(chunks)
