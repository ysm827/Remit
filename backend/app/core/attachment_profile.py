"""多格式附件画像；未知格式保留文件与读取提示，不伪装为已解析表格。"""

import json
import zipfile
from pathlib import Path
from typing import Any


def _profile_mat(path: Path) -> dict[str, Any]:
    """兼容经典 MAT 与 v7.3；对象存储维度不冒充真实表格行列。"""
    import h5py
    from scipy.io import whosmat

    if not h5py.is_hdf5(path):
        return {
            "status": "parsed",
            "variables": [
                {"name": name, "shape": list(shape), "dtype": dtype}
                for name, shape, dtype in whosmat(path)[:40]
            ],
        }
    variables = []
    with h5py.File(path, "r") as source:
        for name in source:
            if name.startswith("#"):
                continue
            # 不跟随附件里的外部/软链接，也不加载整个数据集或对象引用。
            if not isinstance(source.get(name, getlink=True), h5py.HardLink):
                continue
            value = source[name]
            dtype = value.attrs.get("MATLAB_class", b"unknown")
            dtype = (
                dtype.decode("utf-8", errors="replace")
                if isinstance(dtype, bytes)
                else str(dtype)
            )
            item: dict[str, Any] = {"name": name, "dtype": dtype}
            if isinstance(value, h5py.Dataset):
                item["storage_shape"] = list(value.shape)
                if dtype in {
                    "double",
                    "single",
                    "logical",
                    "char",
                    "cell",
                    "int8",
                    "uint8",
                    "int16",
                    "uint16",
                    "int32",
                    "uint32",
                    "int64",
                    "uint64",
                }:
                    item["shape"] = list(reversed(value.shape))
            variables.append(item)
            if len(variables) >= 40:
                break
    return {
        "status": "metadata_only",
        "mat_version": "7.3",
        "variables": variables,
        "reader_hint": "已识别 MATLAB v7.3/HDF5 变量，尚未展开数据；table 等对象须用 MATLAB load 读取，或读取配套 CSV。storage_shape 是存储布局，不是表格行列数。",
    }


def profile_attachment(path: Path) -> dict[str, Any]:
    """读取结构、变量或媒体元数据，避免执行附件内代码。"""
    suffix = path.suffix.lower()
    result: dict[str, Any] = {
        "file": path.name,
        "format": suffix.lstrip(".") or "binary",
        "bytes": path.stat().st_size,
        "rows": 0,
        "columns_count": 0,
        "columns": [],
        "sample_rows": [],
        "status": "metadata_only",
        "reader_hint": "原始附件已保留；编程手须确认实际格式并选择读取器。",
    }
    if suffix in {".pdf", ".docx", ".doc"}:
        if path.stat().st_size > 25 * 1024 * 1024:
            result["reader_hint"] = "文档超过 25MB，保留原件，请拆分后读取。"
            return result
        from app.utils.document_parser import parse_word_bytes
        from app.utils.pdf_parser import parse_problem_pdf_bytes

        parsed = (
            parse_problem_pdf_bytes(path.read_bytes())
            if suffix == ".pdf"
            else parse_word_bytes(path.read_bytes(), suffix)
        )
        result.update(
            status="parsed",
            preview=parsed.text[:12000],
            char_count=parsed.char_count,
            truncated=parsed.char_count > 12000,
            reader_hint="已提取文档文字；可按需读取保留的完整原件。",
        )
    elif suffix in {".json", ".geojson", ".jsonl", ".ndjson"}:
        with path.open(encoding="utf-8-sig") as stream:
            if suffix in {".jsonl", ".ndjson"}:
                value = [
                    json.loads(line)
                    for _, line in zip(range(100), stream)
                    if line.strip()
                ]
                result["sampled"] = True
            else:
                value = json.load(stream)
        result.update(
            status="parsed",
            structure=type(value).__name__,
            preview=json.dumps(value, ensure_ascii=False)[:3000],
        )
        if isinstance(value, list):
            result["rows"] = len(value)
        elif isinstance(value, dict):
            result["keys"] = list(value)[:40]
    elif suffix in {".npy", ".npz"}:
        import numpy as np

        value = np.load(
            path, allow_pickle=False, mmap_mode="r" if suffix == ".npy" else None
        )
        if suffix == ".npy":
            result["arrays"] = [
                {
                    "name": path.stem,
                    "shape": list(value.shape),
                    "dtype": str(value.dtype),
                }
            ]
        else:
            with zipfile.ZipFile(path) as archive:
                if (
                    sum(item.file_size for item in archive.infolist())
                    > 100 * 1024 * 1024
                ):
                    value.close()
                    raise ValueError("NPZ 展开后过大，跳过自动画像")
            with value:
                result["arrays"] = [
                    {
                        "name": name,
                        "shape": list(value[name].shape),
                        "dtype": str(value[name].dtype),
                    }
                    for name in value.files[:40]
                ]
        result["status"] = "parsed"
    elif suffix == ".mat":
        result.update(_profile_mat(path))
    elif suffix in {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"}:
        from PIL import Image

        with Image.open(path) as image:
            result.update(
                status="parsed",
                width=image.width,
                height=image.height,
                mode=image.mode,
                frames=getattr(image, "n_frames", 1),
                reader_hint="这里只读取图像元数据；建模信息需视觉识别或图像处理。",
            )
    elif suffix == ".zip":
        with zipfile.ZipFile(path) as archive:
            members = archive.infolist()
            result.update(
                status="parsed",
                member_count=len(members),
                unpacked_bytes=sum(item.file_size for item in members),
                members=[item.filename for item in members[:100]],
                reader_hint="已读取目录，未自动解压。编程手应按需解压并检查目录穿越与解压总量。",
            )
    elif suffix in {".md", ".dat", ".yaml", ".yml", ".xml", ".kml", ".prj", ".rtf"}:
        with path.open(encoding="utf-8-sig", errors="replace") as stream:
            result.update(status="sampled", preview=stream.read(3000))
    return result
