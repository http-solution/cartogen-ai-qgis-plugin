"""PLAN-023 R11-1: reading a .model3 and refusing any model that holds something not approved. Hand-written model files (a two-step approved model, and the same file with one
thing changed), no QGIS and no numpy needed. The real QGIS writer is checked in test_model_tool_live.py."""
import unittest

from cartogen_ai.core.agent.tools import model_ops as mo


def child(child_id, alg_id, params="", description=None, key="alg_id"):
    return f"""
  <Option name="{child_id}" type="Map">
   <Option value="true" name="active" type="bool"/>
   <Option value="{alg_id}" name="{key}" type="QString"/>
   <Option value="{description or child_id}" name="component_description" type="QString"/>
   <Option value="{child_id}" name="id" type="QString"/>
   <Option name="params" type="Map">{params}
   </Option>
  </Option>"""


def source(kind, **values):
    body = "".join(f'<Option value="{v}" name="{k}" type="QString"/>' for k, v in values.items())
    return f'<Option type="Map"><Option value="{kind}" name="source" type="int"/>{body}</Option>'


def model(children, extra=""):
    return f"""<!DOCTYPE model>
<Option type="Map">
 <Option value="two_step" name="model_name" type="QString"/>
 <Option name="children" type="Map">{children}
 </Option>{extra}
</Option>"""


BUFFER = child("buffer1", "native:buffer", f'<Option name="DISTANCE" type="List">{source(2, static_value="100")}</Option>'
               f'<Option name="INPUT" type="List">{source(0, parameter_name="INPUT")}</Option>', "Buffer")
CENTROIDS = child("centroids1", "native:centroids", f'<Option name="INPUT" type="List">{source(1, child_id="buffer1", output_name="OUTPUT")}</Option>', "Centroids")


class TestAccepted(unittest.TestCase):
    def test_a_two_step_approved_model_is_read_and_accepted(self):
        parsed, error = mo.parse_model(model(BUFFER + CENTROIDS))
        self.assertIsNone(error)
        self.assertEqual(parsed["name"], "two_step")
        self.assertEqual([c["algorithm"] for c in parsed["children"]], ["native:buffer", "native:centroids"])
        self.assertEqual(parsed["algorithm_ids"], ["native:buffer", "native:centroids"])
        self.assertEqual(parsed["children"][0]["parameters"]["DISTANCE"][0]["static_value"], "100")
        self.assertIsNone(mo.check_model(parsed))

    def test_algorithm_id_is_also_read_under_its_other_key(self):
        parsed, _ = mo.parse_model(model(child("b1", "native:buffer", key="algorithm_id")))
        self.assertEqual(parsed["algorithm_ids"], ["native:buffer"])


class TestRefused(unittest.TestCase):
    def check(self, children, extra=""):
        parsed, error = mo.parse_model(model(children, extra))
        self.assertIsNone(error)
        return mo.check_model(parsed)

    def test_a_python_script_or_another_model_is_refused_by_name(self):
        text = self.check(BUFFER + child("s1", "script:dosomething", description="My script"))
        self.assertIn("script:dosomething", text)
        self.assertIn("Python script", text)
        self.assertIn("My script", text)
        self.assertIn("another model", self.check(child("m1", "model:othermodel")))

    def test_an_algorithm_that_is_not_on_the_list_is_refused_by_name(self):
        text = self.check(BUFFER + child("x1", "native:notarealapprovedalgorithm"))
        self.assertIn("native:notarealapprovedalgorithm", text)
        self.assertIn("not on the approved algorithm list", text)

    def test_an_algorithm_that_changes_the_users_layer_is_refused(self):
        self.assertIn("changes the user's own layer", self.check(child("sel", "native:selectbylocation")))

    def test_an_id_hidden_outside_the_children_is_still_found(self):
        extra = '<Option name="other" type="Map"><Option value="script:sneaky" name="alg_id" type="QString"/></Option>'
        self.assertIn("script:sneaky", self.check(BUFFER, extra))

    def test_an_expression_that_calls_a_denied_function_is_refused_naming_the_step(self):
        bad = source(3, expression="eval('1')")
        step = child("e1", "native:extractbyexpression", f'<Option name="EXPRESSION" type="List">{bad}</Option>', "Extract big ones")
        text = self.check(step)
        self.assertIn("Extract big ones", text)
        self.assertIn("eval()", text)

    def test_a_static_expression_parameter_is_screened_too(self):
        step = child("e1", "native:extractbyexpression", f'<Option name="EXPRESSION" type="List">{source(2, static_value="eval(1)")}</Option>')
        self.assertIn("eval()", self.check(step))

    def test_a_raw_backend_text_parameter_is_refused(self):
        step = child("g1", "native:buffer", f'<Option name="EXTRA" type="List">{source(2, static_value="-co X=Y")}</Option>')
        self.assertIn("EXTRA", self.check(step))

    def test_too_many_steps(self):
        many = "".join(child(f"b{i}", "native:buffer") for i in range(mo.MAX_CHILDREN + 1))
        self.assertIn("more than", self.check(many))


class TestUnreadable(unittest.TestCase):
    def test_bad_files_are_refused_before_anything_else(self):
        cases = {"": "empty", "   ": "empty", "not xml at all": "not valid XML", "<a/>": "does not look like", "<Option type=\"Map\"/>": "no steps",
                 "x" * (mo.MAX_BYTES + 1): "larger than"}
        for text, word in cases.items():
            parsed, error = mo.parse_model(text)
            self.assertIsNone(parsed)
            self.assertIn(word, error, text[:20])
        self.assertIn("empty", mo.parse_model(None)[1])

    def test_an_xml_entity_declaration_is_refused(self):
        bomb = '<!DOCTYPE model [<!ENTITY a "aaaa"><!ENTITY b "&a;&a;&a;&a;">]>' + model(BUFFER).split("\n", 1)[1]
        self.assertIn("XML entity", mo.parse_model(bomb)[1])
        self.assertIn("XML entity", mo.parse_model(bomb.replace("<!ENTITY", "<! ENTITY"))[1])

    def test_a_file_nested_absurdly_deep_is_refused_not_a_crash(self):
        deep = '<Option type="Map">' + '<Option name="n" type="Map">' * 3000 + "</Option>" * 3001
        parsed, error = mo.parse_model(deep)
        self.assertIsNone(parsed)
        self.assertTrue(error)

    def test_a_step_without_a_readable_algorithm_refuses_the_whole_model(self):
        broken = '<Option name="odd" type="Map"><Option value="x" name="something_else" type="QString"/></Option>'
        parsed, error = mo.parse_model(model(BUFFER + broken))
        self.assertIsNone(parsed)
        self.assertIn("odd", error)
        self.assertIn("no algorithm id that can be read", error)


if __name__ == "__main__":
    unittest.main()
