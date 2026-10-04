# -*- coding: utf-8 -*-
"""
Native QGIS Processing Provider and Algorithms for Cartogen AI.
Exposes optimal hub siting and multi-band service area calculations to QGIS Processing.
"""

try:
    from qgis.core import (
        QgsProcessing,
        QgsProcessingProvider,
        QgsProcessingAlgorithm,
        QgsProcessingParameterFeatureSource,
        QgsProcessingParameterFeatureSink,
        QgsProcessingParameterNumber,
        QgsProcessingParameterField,
        QgsProcessingParameterEnum,
        QgsProcessingParameterString,
        QgsFeatureSink,
        QgsFields,
        QgsField,
        QgsFeature,
        QgsDistanceArea,
        QgsFeatureRequest,
        QgsPointXY,
        QgsCoordinateTransform,
        QgsProcessingException,
    )
    from qgis.PyQt.QtCore import QCoreApplication, QVariant
    from qgis.PyQt.QtGui import QIcon
    try:
        import processing
    except ImportError:
        processing = None
    QGIS_PROCESSING_AVAILABLE = True
except ImportError:
    QGIS_PROCESSING_AVAILABLE = False
    class QgsProcessing:
        TypeVectorPoint = 0
        TypeVectorLine = 1
    class QgsProcessingProvider:
        pass
    class QgsProcessingAlgorithm:
        pass
    class QCoreApplication:
        @staticmethod
        def translate(context, string):
            return string
    class QIcon:
        pass


# Largest candidates x demand-points product the exact ranking will attempt (~25 million ellipsoidal distance measurements, i.e.
# about a minute or two). Above it the algorithm stops with an explicit message instead of freezing QGIS (#157, audit F21).
MAX_DISTANCE_PAIRS = 25_000_000
_CANCEL_CHECK_EVERY = 2000


def pair_limit_error(candidates, demand, limit=None):
    """Error text when candidates x demand exceeds the limit (default: MAX_DISTANCE_PAIRS, read at call time), else None. Pure."""
    if limit is None:
        limit = MAX_DISTANCE_PAIRS
    pairs = int(candidates) * int(demand)
    if pairs > limit:
        return (f"{candidates:,} candidates x {demand:,} demand points is {pairs:,} distance measurements, above the limit of "
                f"{limit:,}. Filter the candidates or the demand points (for example to one region) and run it again.")
    return None


def child_travel_cost(strategy_index, cost):
    """The travel cost to hand to native:serviceareafrompoint. Pure.

    This algorithm's parameter is METRES for Shortest and SECONDS for Fastest; the child algorithm's cost for the fastest strategy is
    in HOURS (the repo's own calculate_service_area reports hours), so seconds are converted. Before #156 (audit F20) the seconds
    were passed through unchanged, which made every 'Fastest' service area 3,600 times too large."""
    return float(cost) / 3600.0 if int(strategy_index) == 1 else float(cost)


class OptimalHubSitingAlgorithm(QgsProcessingAlgorithm):
    INPUT_CANDIDATES = "INPUT_CANDIDATES"
    INPUT_DEMAND = "INPUT_DEMAND"
    MAX_DISTANCE = "MAX_DISTANCE"
    OUTPUT = "OUTPUT"

    def tr(self, string):
        return QCoreApplication.translate("OptimalHubSitingAlgorithm", string)

    def createInstance(self):
        return OptimalHubSitingAlgorithm()

    def name(self):
        return "optimalhubsiting"

    def displayName(self):
        return self.tr("Optimal Hub Siting (Demand Coverage)")

    def group(self):
        return self.tr("Logistics & Network")

    def groupId(self):
        return "logistics"

    def shortHelpString(self):
        return self.tr(
            "Ranks candidate hub/warehouse/facility point locations by how well they serve a set of demand points "
            "(e.g. villages, health clinics, distribution sites). Computes average geodesic/ellipsoidal distance "
            "and counts demand points within an optional maximum service threshold."
        )

    def initAlgorithm(self, config=None):
        if not QGIS_PROCESSING_AVAILABLE:
            return
        self.addParameter(
            QgsProcessingParameterFeatureSource(
                self.INPUT_CANDIDATES,
                self.tr("Candidate Hub Locations"),
                [QgsProcessing.TypeVectorPoint],
            )
        )
        self.addParameter(
            QgsProcessingParameterFeatureSource(
                self.INPUT_DEMAND,
                self.tr("Demand Points"),
                [QgsProcessing.TypeVectorPoint],
            )
        )
        self.addParameter(
            # A plain number of METRES, not QgsProcessingParameterDistance: that type is in the layer's CRS units (degrees for
            # EPSG:4326), but the distances it is compared with below are ellipsoidal metres, so a threshold typed as 5000 on a
            # geographic layer meant 5000 degrees.
            QgsProcessingParameterNumber(
                self.MAX_DISTANCE,
                self.tr("Maximum Service Distance Threshold (meters, optional)"),
                type=QgsProcessingParameterNumber.Double,
                defaultValue=0.0,
                optional=True,
                minValue=0.0,
            )
        )
        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.OUTPUT,
                self.tr("Ranked Candidates"),
                type=QgsProcessing.TypeVectorPoint,
            )
        )

    def processAlgorithm(self, parameters, context, feedback):
        candidates_source = self.parameterAsSource(parameters, self.INPUT_CANDIDATES, context)
        demand_source = self.parameterAsSource(parameters, self.INPUT_DEMAND, context)
        max_dist = self.parameterAsDouble(parameters, self.MAX_DISTANCE, context)

        if candidates_source is None:
            raise QgsProcessingException(self.invalidSourceError(parameters, self.INPUT_CANDIDATES))
        if demand_source is None:
            raise QgsProcessingException(self.invalidSourceError(parameters, self.INPUT_DEMAND))

        fields = QgsFields(candidates_source.fields())
        fields.append(QgsField("avg_dist_m", QVariant.Double))
        fields.append(QgsField("max_dist_m", QVariant.Double))
        fields.append(QgsField("rank", QVariant.Int))
        if max_dist > 0.0:
            fields.append(QgsField("served_count", QVariant.Int))
            fields.append(QgsField("served_pct", QVariant.Double))

        sink, dest_id = self.parameterAsSink(
            parameters,
            self.OUTPUT,
            context,
            fields,
            candidates_source.wkbType(),
            candidates_source.sourceCrs(),
        )

        if sink is None:
            raise QgsProcessingException(self.invalidSinkError(parameters, self.OUTPUT))

        # #139 / #142 (audit F03, F06): demand points are read as plain points IN THE CANDIDATES' CRS. A demand layer in another
        # CRS used to be measured as if its numbers were in the candidates' CRS (EPSG:3857 metres read as degrees gave ~18
        # million metres for a 557 m gap), and a candidate geometry was asked for hasGeometry(), which a QgsGeometry does not have.
        # Multipart points have no single location, so they are skipped with a warning, never guessed at.
        cand_crs = candidates_source.sourceCrs()
        demand_crs = demand_source.sourceCrs()
        to_cand_crs = None
        if demand_crs.isValid() and cand_crs.isValid() and demand_crs != cand_crs:
            to_cand_crs = QgsCoordinateTransform(demand_crs, cand_crs, context.transformContext())

        demand_points = []
        skipped_demand = 0
        for f in demand_source.getFeatures():
            if not f.hasGeometry() or f.geometry().isEmpty():
                continue
            geom = f.geometry()
            if geom.isMultipart():
                skipped_demand += 1
                continue
            pt = QgsPointXY(geom.asPoint())
            if to_cand_crs is not None:
                try:
                    pt = to_cand_crs.transform(pt)
                except Exception as e:
                    raise QgsProcessingException(
                        f"Could not transform a demand point from {demand_crs.authid()} to {cand_crs.authid()}: {e}")
            demand_points.append(pt)
        if skipped_demand:
            feedback.pushWarning(f"{skipped_demand} multipart demand feature(s) skipped: only single-point features are supported.")
        if not demand_points:
            raise QgsProcessingException("Demand source contains no valid single-point features")

        # Geodesic distance calculation setup
        da = QgsDistanceArea()
        da.setSourceCrs(cand_crs, context.transformContext())
        project_ellipsoid = context.project().ellipsoid() if context.project() else "WGS84"
        da.setEllipsoid(project_ellipsoid if project_ellipsoid and project_ellipsoid != "NONE" else "WGS84")

        scored_candidates = []
        cancelled = False
        cand_features = list(candidates_source.getFeatures())
        too_many = pair_limit_error(len(cand_features), len(demand_points))     # featureCount() can be -1 for some sources
        if too_many:
            raise QgsProcessingException(too_many)
        total_cands = len(cand_features)
        skipped_candidates = 0

        for idx, cand_feat in enumerate(cand_features):
            if feedback.isCanceled():
                cancelled = True
                break
            cand_geom = cand_feat.geometry()
            if not cand_feat.hasGeometry() or cand_geom.isEmpty():
                continue
            if cand_geom.isMultipart():
                skipped_candidates += 1
                continue

            pt = QgsPointXY(cand_geom.asPoint())
            distances = []
            for start in range(0, len(demand_points), _CANCEL_CHECK_EVERY):
                if feedback.isCanceled():
                    cancelled = True
                    break
                distances.extend(da.measureLine(pt, dp) for dp in demand_points[start:start + _CANCEL_CHECK_EVERY])
            if cancelled:
                break    # this candidate's distances are incomplete, so it is not ranked
            avg_dist = sum(distances) / len(distances) if distances else 0.0
            max_d = max(distances) if distances else 0.0

            cand_data = {
                "feat": cand_feat,
                "avg_dist": avg_dist,
                "max_dist": max_d,
            }
            if max_dist > 0.0:
                served = sum(1 for d in distances if d <= max_dist)
                cand_data["served"] = served
                cand_data["pct"] = (served / len(distances) * 100.0) if distances else 0.0

            scored_candidates.append(cand_data)
            feedback.setProgress(int((idx + 1) / total_cands * 50))

        scored_candidates.sort(key=lambda item: item["avg_dist"])

        for rank, item in enumerate(scored_candidates, start=1):
            old_feat = item["feat"]
            new_feat = QgsFeature(fields)
            new_feat.setGeometry(old_feat.geometry())
            new_attrs = list(old_feat.attributes())
            new_attrs.append(round(item["avg_dist"], 2))
            new_attrs.append(round(item["max_dist"], 2))
            new_attrs.append(rank)
            if max_dist > 0.0:
                new_attrs.append(item["served"])
                new_attrs.append(round(item["pct"], 1))
            new_feat.setAttributes(new_attrs)
            if not sink.addFeature(new_feat, QgsFeatureSink.FastInsert):
                raise QgsProcessingException(self.writeFeatureError(sink, parameters, self.OUTPUT))

        if cancelled:
            feedback.pushWarning(f"Cancelled: {len(scored_candidates)} of {len(cand_features)} candidates were ranked. The output is "
                                 "PARTIAL, and the ranks are only among those candidates.")
        if skipped_candidates:
            feedback.pushWarning(
                f"{skipped_candidates} multipart candidate feature(s) skipped: only single-point features are supported.")
        feedback.setProgress(100)
        return {self.OUTPUT: dest_id}


class CalculateServiceAreaAlgorithm(QgsProcessingAlgorithm):
    INPUT_FACILITIES = "INPUT_FACILITIES"
    INPUT_NETWORK = "INPUT_NETWORK"
    TRAVEL_COST = "TRAVEL_COST"
    STRATEGY = "STRATEGY"
    DEFAULT_SPEED = "DEFAULT_SPEED"
    SPEED_FIELD = "SPEED_FIELD"
    DIRECTION_FIELD = "DIRECTION_FIELD"
    VALUE_FORWARD = "VALUE_FORWARD"
    VALUE_BACKWARD = "VALUE_BACKWARD"
    VALUE_BOTH = "VALUE_BOTH"
    OUTPUT_LINES = "OUTPUT_LINES"

    def tr(self, string):
        return QCoreApplication.translate("CalculateServiceAreaAlgorithm", string)

    def createInstance(self):
        return CalculateServiceAreaAlgorithm()

    def name(self):
        return "calculateservicearea"

    def displayName(self):
        return self.tr("Service Area from Network")

    def group(self):
        return self.tr("Logistics & Network")

    def groupId(self):
        return "logistics"

    def shortHelpString(self):
        return self.tr(
            "Calculates reachable network lines and coverage from one or more facility points along a road network. "
            "Supports shortest (distance) or fastest (time) routing with optional speed and direction fields."
        )

    def initAlgorithm(self, config=None):
        if not QGIS_PROCESSING_AVAILABLE:
            return
        self.addParameter(
            QgsProcessingParameterFeatureSource(
                self.INPUT_FACILITIES,
                self.tr("Facility Point Locations"),
                [QgsProcessing.TypeVectorPoint],
            )
        )
        self.addParameter(
            QgsProcessingParameterFeatureSource(
                self.INPUT_NETWORK,
                self.tr("Road / Transport Network"),
                [QgsProcessing.TypeVectorLine],
            )
        )
        self.addParameter(
            QgsProcessingParameterNumber(
                self.TRAVEL_COST,
                self.tr("Travel Cost (metres for Shortest, seconds for Fastest)"),
                type=QgsProcessingParameterNumber.Double,
                defaultValue=1000.0,
                minValue=0.0,
            )
        )
        self.addParameter(
            QgsProcessingParameterEnum(
                self.STRATEGY,
                self.tr("Optimization Strategy"),
                options=[self.tr("Shortest (Distance)"), self.tr("Fastest (Time)")],
                defaultValue=0,
            )
        )
        self.addParameter(
            QgsProcessingParameterNumber(
                self.DEFAULT_SPEED,
                self.tr("Default Speed (km/h)"),
                type=QgsProcessingParameterNumber.Double,
                defaultValue=50.0,
                minValue=1.0,
            )
        )
        self.addParameter(
            QgsProcessingParameterField(
                self.SPEED_FIELD,
                self.tr("Speed Field on Network Layer (Optional)"),
                optional=True,
                parentLayerParameterName=self.INPUT_NETWORK,
            )
        )
        self.addParameter(
            QgsProcessingParameterField(
                self.DIRECTION_FIELD,
                self.tr("Direction Field on Network Layer (Optional)"),
                optional=True,
                parentLayerParameterName=self.INPUT_NETWORK,
            )
        )
        for name, label in ((self.VALUE_FORWARD, "Direction Field Value: forward only (optional)"),
                            (self.VALUE_BACKWARD, "Direction Field Value: backward only (optional)"),
                            (self.VALUE_BOTH, "Direction Field Value: both ways (optional)")):
            self.addParameter(QgsProcessingParameterString(name, self.tr(label), optional=True))
        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.OUTPUT_LINES,
                self.tr("Reachable Network Lines"),
                type=QgsProcessing.TypeVectorLine,
            )
        )

    def processAlgorithm(self, parameters, context, feedback):
        facilities_source = self.parameterAsSource(parameters, self.INPUT_FACILITIES, context)
        network_source = self.parameterAsSource(parameters, self.INPUT_NETWORK, context)
        cost = self.parameterAsDouble(parameters, self.TRAVEL_COST, context)
        strategy_idx = self.parameterAsInt(parameters, self.STRATEGY, context)
        default_speed = self.parameterAsDouble(parameters, self.DEFAULT_SPEED, context)
        speed_field = self.parameterAsString(parameters, self.SPEED_FIELD, context)
        direction_field = self.parameterAsString(parameters, self.DIRECTION_FIELD, context)

        if facilities_source is None:
            raise QgsProcessingException(self.invalidSourceError(parameters, self.INPUT_FACILITIES))
        if network_source is None:
            raise QgsProcessingException(self.invalidSourceError(parameters, self.INPUT_NETWORK))
        direction_values = {key: self.parameterAsString(parameters, key, context)
                            for key in (self.VALUE_FORWARD, self.VALUE_BACKWARD, self.VALUE_BOTH)}

        facility_features = [f for f in facilities_source.getFeatures() if f.hasGeometry() and not f.geometry().isEmpty()]
        total = len(facility_features)
        if not total:
            raise QgsProcessingException("The facilities source has no features with a point geometry")

        # #140 (audit F04): materialize() takes a QgsFeatureRequest; the old code handed it a
        # QgsProcessingFeatureSourceDefinition and raised TypeError before the per-facility try block. Done once, outside the loop,
        # so selected-feature / filter semantics of the Processing source apply and the road graph input is built a single
        # time. The returned temporary layer stays referenced for the whole run.
        network_layer = network_source.materialize(QgsFeatureRequest())
        if network_layer is None:
            raise QgsProcessingException("Could not read the road network source")

        # #156 (audit F20): facility points are moved into the NETWORK's CRS before they are used as start points (a facility layer
        # in another CRS used to be read as if its numbers were already in the network's CRS), and the cost is converted to what
        # the child algorithm expects (see child_travel_cost).
        net_crs, fac_crs = network_source.sourceCrs(), facilities_source.sourceCrs()
        to_net = None
        if fac_crs.isValid() and net_crs.isValid() and fac_crs != net_crs:
            to_net = QgsCoordinateTransform(fac_crs, net_crs, context.transformContext())
        child_cost = child_travel_cost(strategy_idx, cost)

        sink = dest_id = sink_fields = None
        failures, skipped_multipart, reached = [], 0, 0
        for idx, feat in enumerate(facility_features):
            if feedback.isCanceled():
                feedback.pushWarning(f"Cancelled after {idx} of {total} facilities: the output is PARTIAL.")
                break
            geom = feat.geometry()
            if geom.isMultipart():
                skipped_multipart += 1
                continue
            pt = QgsPointXY(geom.asPoint())
            if to_net is not None:
                try:
                    pt = to_net.transform(pt)
                except Exception as e:
                    failures.append((idx, f"could not transform the facility to {net_crs.authid()}: {e}"))
                    continue
            params = {
                "INPUT": network_layer,
                "STRATEGY": strategy_idx,
                "DEFAULT_SPEED": default_speed,
                "TOLERANCE": 0,
                "START_POINT": f"{pt.x()},{pt.y()}",
                "TRAVEL_COST2": child_cost,
                "OUTPUT_LINES": "memory:",
            }
            if speed_field:
                params["SPEED_FIELD"] = speed_field
            if direction_field:
                params["DIRECTION_FIELD"] = direction_field
                for key, value in direction_values.items():
                    if value:
                        params[key] = value

            try:
                out = processing.run("native:serviceareafrompoint", params, context=context, feedback=feedback)
                lines_layer = out.get("OUTPUT_LINES")
            except Exception as e:
                failures.append((idx, str(e)))
                continue
            if not lines_layer:
                failures.append((idx, "the network algorithm returned no output layer"))
                continue

            if sink is None:
                # The sink schema is what the child algorithm actually returns (it is NOT the road layer's fields: a fixture
                # returned only 'type' and 'start'), plus the id of the facility each line belongs to.
                sink_fields = QgsFields()
                for fld in lines_layer.fields():
                    sink_fields.append(fld)
                sink_fields.append(QgsField("facility_fid", QVariant.LongLong))
                sink, dest_id = self.parameterAsSink(
                    parameters, self.OUTPUT_LINES, context, sink_fields, lines_layer.wkbType(),
                    lines_layer.crs() if lines_layer.crs().isValid() else net_crs)
                if sink is None:
                    raise QgsProcessingException(self.invalidSinkError(parameters, self.OUTPUT_LINES))
            for line_feat in lines_layer.getFeatures():
                new_feat = QgsFeature(sink_fields)
                new_feat.setGeometry(line_feat.geometry())
                new_feat.setAttributes(list(line_feat.attributes()) + [feat.id()])
                if not sink.addFeature(new_feat, QgsFeatureSink.FastInsert):
                    raise QgsProcessingException(self.writeFeatureError(sink, parameters, self.OUTPUT_LINES))
            reached += 1
            feedback.setProgress(int((idx + 1) / total * 100))

        if skipped_multipart:
            feedback.pushWarning(f"{skipped_multipart} multipart facility feature(s) skipped: only single points are supported.")
        for idx, message in failures:
            feedback.pushWarning(f"Facility #{idx} produced no service area: {message}")
        if sink is None:
            detail = f" First error: {failures[0][1]}" if failures else ""
            raise QgsProcessingException(f"No facility produced a service area.{detail}")
        if failures:
            feedback.pushWarning(f"{len(failures)} of {total} facilities failed; the output covers the other {reached}.")
        return {self.OUTPUT_LINES: dest_id}


class CartogenProcessingProvider(QgsProcessingProvider):
    def __init__(self):
        super().__init__()
        self._algs = []

    def id(self):
        return "cartogen"

    def name(self):
        return "Cartogen AI"

    def icon(self):
        return QIcon()

    def longName(self):
        return "Cartogen AI Spatial Algorithms"

    def loadAlgorithms(self):
        self._algs = [
            OptimalHubSitingAlgorithm(),
            CalculateServiceAreaAlgorithm(),
        ]
        for alg in self._algs:
            self.addAlgorithm(alg)
