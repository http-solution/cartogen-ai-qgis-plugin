"""Moved to cartogen_ai.core._background_processing (PLAN-040): the validators and models use it and may not import the tools package. This path stays
as an alias to the same module object so old imports and mock.patch targets keep working."""
import sys

from ... import _background_processing as _moved

sys.modules[__name__] = _moved
