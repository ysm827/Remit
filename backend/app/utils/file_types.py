"""Shared file-type rules for uploaded modeling datasets."""

from pathlib import Path


DATA_FILE_SUFFIXES = frozenset(
    {
        ".blocks",
        ".nets",
        ".pl",
        ".csv",
        ".tsv",
        ".tab",
        ".txt",
        ".dat",
        ".xls",
        ".xlsx",
        ".xlsm",
        ".ods",
        ".json",
        ".jsonl",
        ".ndjson",
        ".xml",
        ".yaml",
        ".yml",
        ".mat",
        ".npy",
        ".npz",
        ".parquet",
        ".feather",
        ".h5",
        ".hdf5",
        ".hdf",
        ".nc",
        ".sqlite",
        ".db",
        ".geojson",
        ".shp",
        ".shx",
        ".dbf",
        ".prj",
        ".gpkg",
        ".kml",
        ".png",
        ".jpg",
        ".jpeg",
        ".tif",
        ".tiff",
        ".bmp",
        ".webp",
        ".wav",
        ".mp3",
        ".mp4",
        ".avi",
        ".zip",
        ".7z",
        ".rar",
        ".gz",
        ".tar",
        ".pdf",
        ".docx",
        ".doc",
        ".rtf",
        ".md",
    }
)
FONT_FILE_SUFFIXES = frozenset({".otf", ".ttc", ".ttf"})


def is_data_file(filename: str) -> bool:
    """Return whether a filename is a supported modeling dataset."""
    if Path(filename).name.startswith(".") or Path(filename).name in {
        "workflow_state.json",
        "paper_delivery_report.json",
        "all.zip",
    }:
        return False
    return Path(filename).suffix.lower() in DATA_FILE_SUFFIXES


def is_sandbox_upload_file(filename: str) -> bool:
    """Return whether a work-dir file must be copied into the E2B sandbox."""
    suffix = Path(filename).suffix.lower()
    return is_data_file(filename) or suffix in FONT_FILE_SUFFIXES


def input_filenames(root: str | Path) -> set[str]:
    """返回上传清单，未知后缀也可进入画像与计算沙箱。"""
    import json

    path = Path(root) / ".remit-inputs.json"
    try:
        return set(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError, TypeError):
        return set()
