"""The expression screen (core/validators/expression_screen.py): denied names are caught however they are written, ordinary
expressions pass, and every expression this plugin writes itself passes."""
import re
import unittest

from cartogen_ai.core.validators.expression_screen import DENIED_FUNCTIONS, denied_calls, screen_expression


class TestDenied(unittest.TestCase):
    def test_each_denied_function_is_caught(self):
        for name in sorted(DENIED_FUNCTIONS):
            self.assertEqual(denied_calls(f"{name}('X')"), [name], name)

    def test_case_spacing_and_nesting_do_not_hide_a_call(self):
        for text in ("ENV('HOME')", "Env ( 'HOME' )", "concat('a', env('KEY'))", "\"a\" || file_path('x')", "1 + FILE_EXISTS(\n'x')",
                     "if(true, env('K'), 0)", "env/**/('K')", "env -- c\n('K')"):
            self.assertTrue(denied_calls(text), text)

    def test_eval_cannot_be_used_to_build_the_call_later(self):
        self.assertEqual(denied_calls("eval('en' || 'v(\"K\")')"), ["eval"])
        self.assertEqual(denied_calls("eval_template('[% env(\"K\") %]')"), ["eval_template"])

    def test_message_names_the_function(self):
        self.assertIn("env()", screen_expression("env('K')"))


class TestAllowed(unittest.TestCase):
    def test_ordinary_expressions_pass(self):
        for text in ("\"population\" > 1000", "name = 'Amman'", "area($geometry) / 1000000", "\"a\" || ' ' || \"b\"",
                     "CASE WHEN \"x\" > 5 THEN 'high' ELSE 'low' END", "@project_title", "attribute(@parent, 'id')",
                     "aggregate('roads','count',\"id\")", "to_int(regexp_substr(\"code\", '[0-9]+'))"):
            self.assertIsNone(screen_expression(text), text)

    def test_a_denied_name_that_is_only_text_or_a_field_is_not_a_call(self):
        for text in ("name = 'env(HOME)'", "\"env\" = 1", "\"file_path\" IS NULL", "'it''s env(x)'", "/* env('K') */ 1", "-- env('K')\n1",
                     "my_env('x')", "x.env(1)", "@env"):
            self.assertIsNone(screen_expression(text), text)

    def test_empty_input(self):
        self.assertIsNone(screen_expression(""))
        self.assertIsNone(screen_expression(None))


class TestOurOwnExpressionsPass(unittest.TestCase):
    def test_no_expression_literal_in_the_tool_code_calls_a_denied_function(self):
        """Source scan: a denied call written by the plugin itself would break once the screen is wired in everywhere."""
        import os
        root = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
        pattern = re.compile(r"\b(" + "|".join(sorted(DENIED_FUNCTIONS)) + r")\(\s*['\"]")
        hits = []
        for folder, _dirs, files in os.walk(root):
            for name in files:
                if name.endswith(".py"):
                    with open(os.path.join(folder, name), encoding="utf-8") as fh:
                        for number, line in enumerate(fh, 1):
                            if pattern.search(line) and "expression_screen" not in name:
                                hits.append(f"{name}:{number}")
        self.assertEqual(hits, [])


if __name__ == "__main__":
    unittest.main()


class TestEveryModelExpressionEntryPointIsScreened(unittest.TestCase):
    """The tools that take an expression from the model must call screen_expression. Source check so it runs without QGIS; the live
    counterpart is tests/test_expression_screen_live.py."""

    def test_entry_points(self):
        import ast
        import os
        path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src", "cartogen_ai", "core", "agent",
                            "tools", "vector_tools.py")
        with open(path, encoding="utf-8") as fh:
            source = fh.read()
        functions = {n.name: ast.get_source_segment(source, n)
                     for n in ast.walk(ast.parse(source)) if isinstance(n, ast.FunctionDef)}
        for name in ("run_query", "highlight_features", "apply_labels", "_add_calculated_field", "zoom_to_feature"):
            self.assertIn("screen_expression(", functions[name], f"{name} does not screen the model's expression")
