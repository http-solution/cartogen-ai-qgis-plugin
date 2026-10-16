"""Packages H and I start with a measurement, not a guess: what does the QGIS in CI offer for the layer types and algorithm providers the
plan wants to add? This test prints one `CAPABILITY key=value` line per fact (the job log is the report) and fails only when the probe
itself cannot run. It asserts nothing about what is or is not installed; the findings go into docs/QGIS_CAPABILITY_PROBE_2026-10-16.md and
decide what H and I build."""
import os
import shutil
import unittest

try:
    import qgis.core as core
    from qgis.core import Qgis, QgsApplication, QgsProviderRegistry
    LIVE = True
except ImportError:
    LIVE = False


def _say(key, value):
    print(f"CAPABILITY {key}={value}", flush=True)


@unittest.skipUnless(LIVE, "requires real QGIS")
class TestCapabilityProbe(unittest.TestCase):
    def setUp(self):
        from tests.test_network_units_live import _boot
        why = _boot()
        if why:
            self.skipTest(why)

    def test_report_what_this_qgis_offers(self):
        _say("qgis_version", Qgis.version())
        try:
            from osgeo import gdal
            _say("gdal_version", gdal.VersionInfo("RELEASE_NAME"))
            drivers = {gdal.GetDriver(i).ShortName for i in range(gdal.GetDriverCount())}
            for name in ("netCDF", "GRIB", "HDF5", "HDF4", "ECW", "JP2ECW", "MrSID", "PDF", "GTiff", "COG", "Zarr", "FileGDB", "OpenFileGDB"):
                _say(f"gdal_driver_{name}", name in drivers)
        except ImportError:
            _say("gdal_python", "missing")
        providers = sorted(QgsProviderRegistry.instance().providerList())
        _say("data_providers", ",".join(providers))
        for cls in ("QgsPointCloudLayer", "QgsVectorTileLayer", "QgsTiledSceneLayer", "QgsMeshLayer", "QgsAnnotationLayer", "QgsElevationProfile",
                    "QgsProfileRequest", "QgsLayoutItemElevationProfile", "QgsLayoutItemChart", "QgsLayoutItem3DMap", "QgsRasterContourRenderer",
                    "QgsGpsConnection", "QgsGpsInformation", "QgsProjectElevationProperties", "QgsVirtualLayerDefinition"):
            _say(f"class_{cls}", hasattr(core, cls))
        for module in ("qgis._3d", "qgis._gui", "qgis.analysis"):
            try:
                __import__(module)
                _say(f"module_{module}", True)
            except ImportError as e:
                _say(f"module_{module}", f"missing ({e})")
        registry = QgsApplication.processingRegistry()
        counts = {}
        for algorithm in registry.algorithms():
            counts[algorithm.provider().id()] = counts.get(algorithm.provider().id(), 0) + 1
        _say("processing_providers", ",".join(f"{k}:{v}" for k, v in sorted(counts.items())))
        for binary in ("grass", "grass84", "grass83", "grass82", "saga_cmd", "gdalinfo", "gdal_translate", "pdal", "lastools", "python3"):
            _say(f"binary_{binary}", shutil.which(binary) or "no")
        _say("grass_env", os.environ.get("GISBASE", "unset"))
        grass = registry.providerById("grass")
        _say("grass_provider", "registered" if grass is not None else "absent")
        if grass is not None:
            _say("grass_active", grass.isActive())
            _say("grass_algorithms", len(grass.algorithms()))
        self.assertTrue(providers, "the probe found no data providers at all")


if __name__ == "__main__":
    unittest.main()
