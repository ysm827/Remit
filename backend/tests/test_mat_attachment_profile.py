"""MAT 文件版本与 MATLAB 对象结构的读取边界。"""

import h5py
import numpy as np
from scipy.io import savemat

from app.core.attachment_profile import profile_attachment


def test_classic_mat_keeps_original_dimensions(tmp_path):
    path = tmp_path / "legacy.mat"
    savemat(path, {"dem": np.zeros((3, 5))})
    result = profile_attachment(path)
    assert result["status"] == "parsed"
    assert result["variables"] == [{"name": "dem", "shape": [3, 5], "dtype": "double"}]


def test_v73_objects_do_not_claim_storage_layout_as_table_shape(tmp_path):
    path = tmp_path / "modern.mat"
    with h5py.File(path, "w", userblock_size=512) as source:
        matrix = source.create_dataset("dem", shape=(5, 3), dtype="float32")
        matrix.attrs["MATLAB_class"] = np.bytes_("single")
        table = source.create_dataset("data", shape=(1, 6), dtype="uint32")
        table.attrs["MATLAB_class"] = np.bytes_("table")
        source.create_group("#refs#")
        source["external"] = h5py.ExternalLink("missing.h5", "/secret")
        source["soft"] = h5py.SoftLink("/dem")
    result = profile_attachment(path)
    variables = {item["name"]: item for item in result["variables"]}
    assert set(variables) == {"dem", "data"}
    assert variables["dem"]["shape"] == [3, 5]
    assert variables["data"]["dtype"] == "table"
    assert variables["data"]["storage_shape"] == [1, 6]
    assert "shape" not in variables["data"]
    assert result["status"] == "metadata_only"
    assert result["mat_version"] == "7.3"
