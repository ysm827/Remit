import tempfile
import unittest
from pathlib import Path
from app.tools.matlab_interpreter import MatlabCodeInterpreter, MatlabUnavailableError


class MatlabRootTests(unittest.TestCase):
    def test_launcher_and_architecture_paths_share_validated_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "extern/engines/python").mkdir(parents=True)
            for suffix in ("bin/matlab.exe", "bin/win64/MATLAB.exe", "bin/glnxa64/MATLAB", "bin/maca64/MATLAB", "bin/maci64/MATLAB"):
                interpreter = object.__new__(MatlabCodeInterpreter)
                interpreter.executable = str(root / suffix)
                self.assertEqual(interpreter.matlab_root, root.resolve())
            interpreter.executable = str(root / "unrelated/MATLAB.exe")
            with self.assertRaises(MatlabUnavailableError):
                _ = interpreter.matlab_root

    def test_invalid_installation_is_not_silently_accepted(self):
        with tempfile.TemporaryDirectory() as tmp:
            interpreter = object.__new__(MatlabCodeInterpreter)
            interpreter.executable = str(Path(tmp) / "bin/win64/MATLAB.exe")
            with self.assertRaisesRegex(MatlabUnavailableError, "Engine"):
                _ = interpreter.matlab_root
