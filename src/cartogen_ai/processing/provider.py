# -*- coding: utf-8 -*-
"""
Native QGIS Processing Provider and Algorithms for Cartogen AI.
Exposes optimal hub siting and multi-band service area calculations to QGIS Processing.
"""

try:
    from qgis.core import (
        QgsProcessingProvider,
        QgsProcessingAlgorithm,
        QgsProcessingParameterFeatureSource,
        QgsProcessingParameterFeatureSink,
        QgsProcessingParameterDistance,
        QgsProcessingParameterNumber,
        QgsProcessingParameterField,
        QgsProcessingParameterEnum,
        QgsProcessingParameterString,
        QgsProcessingOutputNumber,
        QgsProcessingOutputString,
        QgsProcessingContext,
        QgsProcessingFeedback,
        QgsFeatureSink,
        QgsFields,
        QgsField,
        QgsFeature,
        QgsWkbTypes,
        QgsDistanceArea,
        QgsProject,
        QgsProcessingFeatureSourceDefinition,
        Qgis,
    )
    from qgis.PyQt.QtCore import QCoreApplication, QVariant
    from qgis.PyQt.QtGui import QIcon
    import processing
    QGIS_PROCESSING_AVAILABLE = True
except ImportError:
    QGIS_PROCESSING_AVAILABLE = False
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
                [QgsProcessingAlgorithm.TypeVectorPoint],
            )
        )
        self.addParameter(
            QgsProcessingParameterFeatureSource(
                self.INPUT_DEMAND,
                self.tr("Demand Points"),
                [QgsProcessingAlgorithm.TypeVectorPoint],
            )
        )
        self.addParameter(
            QgsProcessingParameterDistance(
                self.MAX_DISTANCE,
                self.tr("Maximum Service Distance Threshold (Optional)"),
                defaultValue=0.0,
                optional=True,
                minValue=0.0,
            )
        )
        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.OUTPUT,
                self.tr("Ranked Candidates"),
                type=QgsProcessingAlgorithm.TypeVectorPoint,
            )
        )

    def processAlgorithm(self, parameters, context, feedback):
        candidates_source = self.parameterAsSource(parameters, self.INPUT_CANDIDATES, context)
        demand_source = self.parameterAsSource(parameters, self.INPUT_DEMAND, context)
        max_dist = self.parameterAsDouble(parameters, self.MAX_DISTANCE, context)

        if candidates_source is None:
            raise RuntimeError("Invalid candidate hub locations source")
        if demand_source is None:
            raise RuntimeError("Invalid demand points source")

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

        demand_geoms = [f.geometry() for f in demand_source.getFeatures() if f.hasGeometry() and not f.geometry().isEmpty()]
        if not demand_geoms:
            raise RuntimeError("Demand source contains no valid features")

        # Geodesic distance calculation setup
        da = QgsDistanceArea()
        da.setSourceCrs(candidates_source.sourceCrs(), context.transformContext())
        project_ellipsoid = context.project().ellipsoid() if context.project() else "WGS84"
        da.setEllipsoid(project_ellipsoid if project_ellipsoid and project_ellipsoid != "NONE" else "WGS84")

        scored_candidates = []
        cand_features = list(candidates_source.getFeatures())
        total_cands = len(cand_features)

        for idx, cand_feat in enumerate(cand_features):
            if feedback.isCanceled():
                break
            cand_geom = cand_feat.geometry()
            if not cand_geom.hasGeometry() or cand_geom.isEmpty():
                continue

            pt = cand_geom.asPoint()
            distances = [da.measureLine(pt, dg.asPoint()) for dg in demand_geoms]
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
            if feedback.isCanceled():
                break
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
            sink.addFeature(new_feat, QgsFeatureSink.FastInsert)

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
                [QgsProcessingAlgorithm.TypeVectorPoint],
            )
        )
        self.addParameter(
            QgsProcessingParameterFeatureSource(
                self.INPUT_NETWORK,
                self.tr("Road / Transport Network"),
                [QgsProcessingAlgorithm.TypeVectorLine],
            )
        )
        self.addParameter(
            QgsProcessingParameterNumber(
                self.TRAVEL_COST,
                self.tr("Travel Cost (meters for Shortest, seconds for Fastest)"),
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
        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.OUTPUT_LINES,
                self.tr("Reachable Network Lines"),
                type=QgsProcessingAlgorithm.TypeVectorLine,
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
            raise RuntimeError("Invalid facilities source")
        if network_source is None:
            raise RuntimeError("Invalid road network source")

        sink, dest_id = self.parameterAsSink(
            parameters,
            self.OUTPUT_LINES,
            context,
            network_source.fields(),
            QgsWkbTypes.MultiLineString,
            network_source.sourceCrs(),
        )

        facility_features = [f for f in facilities_source.getFeatures() if f.hasGeometry() and not f.geometry().isEmpty()]
        total = len(facility_features)

        for idx, feat in enumerate(facility_features):
            if feedback.isCanceled():
                break
            pt = feat.geometry().asPoint()
            params = {
                "INPUT": network_source.materialize(QgsProcessingFeatureSourceDefinition(parameters[self.INPUT_NETWORK])),
                "STRATEGY": strategy_idx,
                "DEFAULT_SPEED": default_speed,
                "TOLERANCE": 0,
                "START_POINT": f"{pt.x()},{pt.y()}",
                "TRAVEL_COST2": cost,
                "OUTPUT_LINES": "memory:",
            }
            if speed_field:
                params["SPEED_FIELD"] = speed_field
            if direction_field:
                params["DIRECTION_FIELD"] = direction_field

            try:
                out = processing.run("native:serviceareafrompoint", params, context=context, feedback=feedback)
                lines_layer = out.get("OUTPUT_LINES")
                if lines_layer:
                    for line_feat in lines_layer.getFeatures():
                        sink.addFeature(line_feat, QgsFeatureSink.FastInsert)
            except Exception as e:
                feedback.pushWarning(f"Facility #{idx} skipped: {e}")

            feedback.setProgress(int((idx + 1) / total * 100))

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
