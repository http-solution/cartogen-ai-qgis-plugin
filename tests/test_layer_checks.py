import unittest

from cartogen_ai.core.agent.tools._layer_checks import require_valid_layer


class _Layer:
    def __init__(self, valid):
        self._valid = valid

    def isValid(self):
        return self._valid


class TestRequireValidLayer(unittest.TestCase):
    def test_returns_a_valid_layer_unchanged(self):
        layer = _Layer(True)
        self.assertIs(require_valid_layer(layer), layer)

    def test_an_invalid_layer_raises_a_readable_error_not_an_attribute_error_later(self):
        with self.assertRaisesRegex(ValueError, "could not create a temporary"):
            require_valid_layer(_Layer(False))


if __name__ == "__main__":
    unittest.main()
