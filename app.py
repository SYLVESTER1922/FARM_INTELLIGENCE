"""Hugging Face Space entry point. Spaces runs `python app.py`; the app must run as `python -m ui.app` (as on Render) so the
chatbot/router/shadow packages resolve from the repo root, so this runs that module as __main__ and nothing else."""

import runpy

import spaces


@spaces.GPU
def _zerogpu_placeholder():
    """ZeroGPU Spaces expect a GPU-decorated function. This app does no GPU work and nothing calls this."""


if __name__ == "__main__":
    runpy.run_module("ui.app", run_name="__main__", alter_sys=True)
