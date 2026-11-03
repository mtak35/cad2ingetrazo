# SPDX-License-Identifier: MIT
"""OpenSKP 1.3.0's .skp writer (create, legacy, _core, _face_groups,
errors and the blank scaffold), MIT licence, by Ahsan Mehmood —
https://github.com/iamahsanmehmood/openskp — carried here (one fix: the face plane offset written as SketchUp stores it)
because older IngeTrazo installers ship an OpenSKP whose writer breaks
past 16,384 objects (a large model's .skp then fails in SketchUp with
«unexpected file format»)."""
from .create import ComponentDefinitionBuilder, SkpBuilder, SkpWriteError, create

__version__ = "1.3.0"
__all__ = ["create", "SkpBuilder", "SkpWriteError", "ComponentDefinitionBuilder"]
