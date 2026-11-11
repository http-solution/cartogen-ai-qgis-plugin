"""PLAN-023 R11-1 in real QGIS: a model written by QGIS's own writer (buffer then centroids) is read by the pure parser and run, its output a new temporary layer while the input layer is unchanged;
models that hold a script, an unapproved algorithm or an algorithm that changes the user's layer are refused naming it, before anything runs; paths outside the project folder, an unsaved
project, wrong input names and an XML entity are refused. Written without a QGIS install: CI's first run is its first execution."""
import os
import tempfile
import unittest

try:
    from qgis.core import (QgsFeature, QgsGeometry, QgsProcessing, QgsProcessingModelAlgorithm, QgsProcessingModelChildAlgorithm, QgsProcessingModelChildParameterSource,
                           QgsProcessingModelOutput, QgsProcessingModelParameter, QgsProcessingParameterFeatureSource, QgsProject, QgsVectorLayer, QgsWkbTypes)
    LIVE = True
except ImportError:
    LIVE = False


def build_model(path, steps):
    """Writes a model whose steps are [(child id, algorithm id, {param: static value})]; the first takes the INPUT, each next takes the previous OUTPUT; the last is a model output. Needs QGIS."""
    model = QgsProcessingModelAlgorithm("two_step", "tests")
    model.setName("two_step")
    model.addModelParameter(QgsProcessingParameterFeatureSource("INPUT", "Input", [QgsProcessing.SourceType.TypeVectorAnyGeometry]), QgsProcessingModelParameter("INPUT"))
    previous = None
    for index, (child_id, alg_id, statics) in enumerate(steps):
        child = QgsProcessingModelChildAlgorithm(alg_id)
        child.setChildId(child_id)
        child.setDescription(child_id)
        source = QgsProcessingModelChildParameterSource.fromModelParameter("INPUT") if previous is None else QgsProcessingModelChildParameterSource.fromChildOutput(previous, "OUTPUT")
        child.addParameterSources("INPUT", [source])
        for name, value in statics.items():
            child.addParameterSources(name, [QgsProcessingModelChildParameterSource.fromStaticValue(value)])
        if index == len(steps) - 1:                                      # the last step's OUTPUT is the model's output
            output = QgsProcessingModelOutput("RESULT", "Result")
            output.setChildId(child_id)
            output.setChildOutputName("OUTPUT")
            child.setModelOutputs({"RESULT": output})
        model.addChildAlgorithm(child)
        previous = child_id
    assert model.toFile(path)
    return model


@unittest.skipUnless(LIVE, "requires real QGIS")
class TestRunProcessingModelLive(unittest.TestCase):
    def setUp(self):
        from tests.test_network_units_live import _boot
        why = _boot()
        if why:
            self.skipTest(why)
        QgsProject.instance().clear()
        self.addCleanup(QgsProject.instance().clear)
        self.dir = tempfile.mkdtemp(prefix="cartogen_model_")
        QgsProject.instance().setFileName(os.path.join(self.dir, "p.qgz"))
        self.layer = QgsVectorLayer("Polygon?crs=EPSG:32636&field=name:string", "src", "memory")
        feats = []
        for i, wkt in enumerate(["POLYGON((0 0,10 0,10 10,0 10,0 0))", "POLYGON((100 0,110 0,110 10,100 10,100 0))"]):
            f = QgsFeature(self.layer.fields())
            f.setGeometry(QgsGeometry.fromWkt(wkt))
            f.setAttributes([f"a{i}"])
            feats.append(f)
        self.layer.dataProvider().addFeatures(feats)
        QgsProject.instance().addMapLayer(self.layer)

    def _run(self, name="two_step.model3", **kw):
        from cartogen_ai.core.agent.tools.model_tool import run_processing_model
        return run_processing_model(name, **kw)

    def _model(self, steps, name="two_step.model3"):
        build_model(os.path.join(self.dir, name), steps)
        return name

    def test_the_pure_parser_reads_a_file_written_by_qgis_itself(self):
        from cartogen_ai.core.agent.tools import model_ops as mo
        self._model([("buffer1", "native:buffer", {"DISTANCE": 10.0}), ("centroids1", "native:centroids", {})])
        with open(os.path.join(self.dir, "two_step.model3"), encoding="utf-8") as fh:
            parsed, error = mo.parse_model(fh.read())
        self.assertIsNone(error)
        self.assertEqual(parsed["algorithm_ids"], ["native:buffer", "native:centroids"])
        self.assertEqual([c["id"] for c in parsed["children"]], ["buffer1", "centroids1"])
        self.assertIsNone(mo.check_model(parsed))

    def test_a_two_step_approved_model_runs_and_gives_a_new_temporary_layer(self):
        self._model([("buffer1", "native:buffer", {"DISTANCE": 10.0}), ("centroids1", "native:centroids", {})])
        out = self._run(inputs={"INPUT": "src"})
        self.assertTrue(out.get("success"), out)
        self.assertEqual((out["steps"], out["algorithms"]), (2, ["native:buffer", "native:centroids"]))
        self.assertEqual(len(out["layers"]), 1)
        result = QgsProject.instance().mapLayersByName(out["layers"][0]["layer_name"])[0]
        self.assertEqual(result.featureCount(), 2)
        self.assertEqual(QgsWkbTypes.geometryType(result.wkbType()), QgsWkbTypes.GeometryType.PointGeometry)
        self.assertEqual(self.layer.featureCount(), 2)                                           # the input layer is unchanged
        self.assertEqual(result.dataProvider().name(), "memory")                                 # a temporary layer, not a file

    def test_a_model_with_a_script_an_unapproved_or_a_selection_algorithm_is_refused_by_name_before_running(self):
        before = len(QgsProject.instance().mapLayers())
        for alg_id in ("script:dosomething", "native:selectbylocation", "native:notarealalgorithm"):
            self._model([("buffer1", "native:buffer", {"DISTANCE": 10.0}), ("bad1", alg_id, {})], name="bad.model3")
            out = self._run("bad.model3", inputs={"INPUT": "src"})
            self.assertIn(alg_id, out["error"], alg_id)
            self.assertTrue(out.get("refused_before_running"), out)
        self.assertEqual(len(QgsProject.instance().mapLayers()), before)

    def test_paths_outside_the_folder_wrong_files_and_an_unsaved_project_are_refused(self):
        self._model([("buffer1", "native:buffer", {"DISTANCE": 10.0})])
        self.assertIn("inside the project folder", self._run("../two_step.model3")["error"])
        self.assertIn("inside the project folder", self._run("/etc/passwd")["error"])
        self.assertIn("ends in .model3", self._run("p.txt")["error"])
        self.assertIn("No model file", self._run("missing.model3")["error"])
        QgsProject.instance().setFileName("")
        self.assertIn("Save the project first", self._run()["error"])

    def test_wrong_and_missing_inputs_are_reported_with_the_models_input_names(self):
        self._model([("buffer1", "native:buffer", {"DISTANCE": 10.0})])
        self.assertIn("INPUT", self._run(inputs={"NOPE": "src"})["error"])
        self.assertIn("not complete", self._run(inputs={})["error"])

    def test_an_xml_entity_in_the_file_is_refused(self):
        self._model([("buffer1", "native:buffer", {"DISTANCE": 10.0})])
        path = os.path.join(self.dir, "two_step.model3")
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        with open(os.path.join(self.dir, "bomb.model3"), "w", encoding="utf-8") as fh:
            fh.write(text.replace("<!DOCTYPE model>", '<!DOCTYPE model [<!ENTITY a "aaaa">]>'))
        self.assertIn("XML entity", self._run("bomb.model3", inputs={"INPUT": "src"})["error"])


if __name__ == "__main__":
    unittest.main()
