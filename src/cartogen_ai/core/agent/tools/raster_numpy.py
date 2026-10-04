# -*- coding: utf-8 -*-
"""
Raster contrast equalisation and unsupervised classification without Processing algorithm ids that QGIS 4.2.2 does not have.

GitHub #162 (audit F26), step 2. The CI registry diagnostic (PR #175) showed `gdal:contraststretch`, `saga:kmeansclassificationforgrid`
and `saga:supervisedclassificationforgrids` are not in the QGIS 4.2.2 registry (no SAGA provider is installed), so
histogram_equalization and unsupervised_classification could never have worked there. They now compute the result with numpy and
write a GeoTIFF with GDAL's Python bindings, both of which ship with QGIS. The numeric kernels (equalize, kmeans) are pure numpy and
unit tested offline; the GDAL read/write is covered by tests/test_raster_numpy_live.py, written without a local QGIS (first run in CI).

Limits, stated: k-means is plain Lloyd's algorithm on the pixel values (optionally the first few bands) with a seeded k-means++
start and a fitted-on-a-sample / assigned-to-all design, not a replacement for a remote-sensing package; equalisation is a global
histogram equalisation of one band to 8 bits.
"""
import os
import tempfile

MAX_BANDS = 8
MAX_PIXELS = 25_000_000          # a larger raster is refused rather than exhausting memory
FIT_SAMPLE = 200_000
ASSIGN_CHUNK = 500_000


def _np():
    import numpy
    return numpy


# ---------------------------------------------------------------- pure numpy --

def equalize(values, valid, levels=256):
    """Histogram-equalised copy of `values` (2-D float array) scaled to 0..levels-1 as uint8/uint16; cells where `valid` is False
    get 0. A band with no variation returns all zeros (nothing to stretch)."""
    np = _np()
    out = np.zeros(values.shape, dtype=np.uint8 if levels <= 256 else np.uint16)
    v = values[valid]
    if v.size == 0 or float(v.max()) == float(v.min()):
        return out
    hist, edges = np.histogram(v, bins=levels)
    cdf = np.cumsum(hist).astype(np.float64)
    first = cdf[np.nonzero(hist)[0][0]]
    if cdf[-1] == first:
        return out
    lut = np.round((cdf - first) / (cdf[-1] - first) * (levels - 1)).clip(0, levels - 1)
    idx = np.clip(np.digitize(v, edges[1:-1], right=False), 0, levels - 1)
    out[valid] = lut[idx].astype(out.dtype)
    return out


def _kmeans_plus_plus(x, k, rng):
    np = _np()
    centers = [x[rng.randint(len(x))]]
    d2 = ((x - centers[0]) ** 2).sum(axis=1)
    for _ in range(1, k):
        total = d2.sum()
        if total <= 0:
            centers.append(x[rng.randint(len(x))])
        else:
            centers.append(x[rng.choice(len(x), p=d2 / total)])
        d2 = np.minimum(d2, ((x - centers[-1]) ** 2).sum(axis=1))
    return np.array(centers, dtype=np.float64)


def _assign(x, centers, chunk=ASSIGN_CHUNK):
    np = _np()
    labels = np.empty(len(x), dtype=np.int32)
    for start in range(0, len(x), chunk):
        block = x[start:start + chunk]
        d = ((block[:, None, :] - centers[None, :, :]) ** 2).sum(axis=2)
        labels[start:start + chunk] = d.argmin(axis=1)
    return labels


def kmeans(pixels, k, iterations=20, seed=0, fit_sample=FIT_SAMPLE):
    """Lloyd's k-means on an (n, bands) float array. Centres are fitted on at most `fit_sample` randomly chosen pixels, then every
    pixel is assigned to its nearest centre. Returns (labels 0..k-1, centres). Reproducible for a seed. An empty cluster is
    re-seeded from the pixel farthest from its centre."""
    np = _np()
    x = np.asarray(pixels, dtype=np.float64)
    if x.ndim != 2 or len(x) < k:
        raise ValueError("need a 2-D array with at least k pixels")
    rng = np.random.RandomState(seed)
    sample = x if len(x) <= fit_sample else x[rng.choice(len(x), fit_sample, replace=False)]
    centers = _kmeans_plus_plus(sample, k, rng)
    for _ in range(int(iterations)):
        labels = _assign(sample, centers)
        new = centers.copy()
        for c in range(k):
            members = sample[labels == c]
            if len(members):
                new[c] = members.mean(axis=0)
            else:
                far = ((sample - centers[labels]) ** 2).sum(axis=1).argmax()
                new[c] = sample[far]
        if np.allclose(new, centers):
            centers = new
            break
        centers = new
    return _assign(x, centers), centers


def validate_class_count(num_classes):
    """Error text for an unusable class count, else None. Pure."""
    try:
        n = int(num_classes)
    except (TypeError, ValueError):
        return "num_classes must be a whole number."
    if not 2 <= n <= 50:
        return "num_classes must be between 2 and 50."
    return None


# ---------------------------------------------------------------- GDAL I/O --

def read_bands(source, bands=None, max_pixels=MAX_PIXELS):
    """(array (rows, cols, nb) float32, valid mask (rows, cols), template info) from a GDAL-readable raster. Raises ValueError with a
    plain message when the raster cannot be read or is too large."""
    try:
        from osgeo import gdal
    except ImportError as e:
        raise ValueError("GDAL's Python bindings are not available in this QGIS.") from e
    ds = gdal.Open(source)
    if ds is None:
        raise ValueError("the raster could not be opened.")
    if ds.RasterXSize * ds.RasterYSize > max_pixels:
        raise ValueError(f"the raster has {ds.RasterXSize * ds.RasterYSize:,} cells, above the {max_pixels:,} limit; clip it first.")
    np = _np()
    wanted = list(bands) if bands else list(range(1, min(ds.RasterCount, MAX_BANDS) + 1))
    layers, valid = [], np.ones((ds.RasterYSize, ds.RasterXSize), dtype=bool)
    for b in wanted:
        band = ds.GetRasterBand(b)
        arr = band.ReadAsArray().astype(np.float32)
        nodata = band.GetNoDataValue()
        valid &= np.isfinite(arr)
        if nodata is not None:
            valid &= arr != np.float32(nodata)
        layers.append(arr)
    info = {"geotransform": ds.GetGeoTransform(), "projection": ds.GetProjection(), "bands_used": wanted}
    return np.stack(layers, axis=-1), valid, info


def write_single_band(array, info, nodata=0):
    """Write a 2-D integer array as a GeoTIFF in a temp file with the template's georeferencing. Returns the path."""
    from osgeo import gdal
    fd, path = tempfile.mkstemp(suffix=".tif")
    os.close(fd)
    rows, cols = array.shape
    gdal_type = gdal.GDT_Byte if array.dtype.itemsize == 1 else gdal.GDT_UInt16
    ds = gdal.GetDriverByName("GTiff").Create(path, cols, rows, 1, gdal_type)
    ds.SetGeoTransform(info["geotransform"])
    ds.SetProjection(info["projection"])
    band = ds.GetRasterBand(1)
    band.WriteArray(array)
    band.SetNoDataValue(nodata)
    band.FlushCache()
    ds = None
    return path
