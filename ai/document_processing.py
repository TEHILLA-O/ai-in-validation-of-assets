"""Source documents are stored. PDF text is not extracted and is not sent to a model."""

from __future__ import annotations


def describe_upload(filename: str, content: bytes) -> str:
    lower = filename.lower()
    if lower.endswith((".csv", ".txt", ".md")):
        return content.decode("utf-8", errors="replace")[:4000]
    if lower.endswith((".xlsx", ".xlsm", ".xls")):
        return "Spreadsheet stored. Figures enter the model only through the statement importer."
    return (
        "This file is stored as a source document. Text extraction is not implemented, "
        "so it was not parsed into financial statements and it is not sent to a language model."
    )
