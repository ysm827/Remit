"""Exercise the real kernel bootstrap and saved figures, without external services."""

import asyncio
from unittest.mock import AsyncMock, patch

from PIL import Image

from app.tools.local_interpreter import LocalCodeInterpreter
from app.tools.notebook_serializer import NotebookSerializer


def test_initialized_kernel_exports_figures_and_preserves_math(tmp_path):
    async def render():
        interpreter = LocalCodeInterpreter(
            "plot-export-test", str(tmp_path), NotebookSerializer(str(tmp_path)), timeout=45
        )
        with patch(
            "app.tools.local_interpreter.redis_manager.publish_message", new=AsyncMock()
        ):
            try:
                await interpreter.initialize()
                interpreter.add_section("plot-export-test")
                output, failed, error = await interpreter.execute_code(
                    "import matplotlib\n"
                    "matplotlib.use('Agg')\n"
                    "import matplotlib.pyplot as plt\n"
                    "fig, ax = plt.subplots()\n"
                    "ax.plot([1,2,3], [2,4,3], label='area (m²)')\n"
                    "title = ax.set_title('volume (m³)')\n"
                    "label = ax.set_xlabel(r'$x^2$')\n"
                    "ax.legend()\n"
                    "fig.savefig('plot.png')\n"
                    "assert title.get_text() == 'volume (m$^3$)'\n"
                    "assert label.get_text() == r'$x^2$'\n"
                    "fig.savefig('plot.pdf')\n"
                    "plt.close(fig)\n"
                    "print('plot export verified')\n"
                )
                assert not failed, error
                assert "plot export verified" in output
            finally:
                await interpreter.cleanup()

    asyncio.run(render())
    with Image.open(tmp_path / "plot.png") as image:
        image.verify()
    assert (tmp_path / "plot.pdf").read_bytes().startswith(b"%PDF-")
