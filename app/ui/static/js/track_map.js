(function () {
    const OFFLINE_LAYERS = [
        {
            id: "world",
            label: "Dünya",
            bounds: [[-85.0, -180.0], [85.0, 180.0]],
            homeCenter: [25.0, 15.0],
            homeZoom: 3,
            minZoom: 2,
            maxZoom: 5,
            maxNativeZoom: 5
        },
        {
            id: "turkiye",
            label: "Türkiye",
            bounds: [[35.8, 25.6], [42.2, 44.9]],
            homeCenter: [39.0, 35.2],
            homeZoom: 7,
            minZoom: 5,
            maxZoom: 10,
            maxNativeZoom: 10
        },
        {
            id: "istanbul",
            label: "İstanbul",
            bounds: [[40.8, 28.45], [41.4, 29.8]],
            homeCenter: [41.05, 29.05],
            homeZoom: 10,
            minZoom: 9,
            maxZoom: 13,
            maxNativeZoom: 13
        },
        {
            id: "tuzla",
            label: "İstanbul/Tuzla",
            bounds: [[40.78, 29.2], [40.95, 29.5]],
            homeCenter: [40.83, 29.31],
            homeZoom: 13,
            minZoom: 12,
            maxZoom: 16,
            maxNativeZoom: 16
        }
    ];
    const DEFAULT_LAYER_ID = "turkiye";
    const GLOBAL_LAYER_BOUNDS = OFFLINE_LAYERS[0].bounds;
    const GLOBAL_MIN_ZOOM = Math.min(...OFFLINE_LAYERS.map((item) => item.minZoom));
    const GLOBAL_MAX_ZOOM = Math.max(...OFFLINE_LAYERS.map((item) => item.maxZoom));
    const ROLE_COLORS = {
        recon: "#6a2ea1",
        interceptor: "#193a8a",
        station: "#f0cb4b",
        hostile: "#ff4e5f",
        airTraffic: "#ffd32a"
    };
    const FIELD_LAYER_COLORS = {
        base_perimeter: "#2d8cff",
        safe_corridor: "#18c47f",
        patrol_area: "#f0cb4b",
        restricted_area: "#ff1f2d",
        custom: "#a855f7"
    };
    const FIELD_LAYER_EFFECT_COLORS = {
        critical: "#ff1f2d",
        high: "#2d8cff",
        medium: "#f0cb4b",
        info: "#18c47f"
    };
    const FIELD_LAYER_EFFECT_RANK = {
        critical: 4,
        high: 3,
        medium: 2,
        info: 1
    };
    const ROLE_FOCUS_COLORS = {
        recon: "#8d53c3",
        interceptor: "#3f66c4",
        station: "#ffe37d",
        hostile: "#ff7a86"
    };

    function distanceMeters(lat1, lon1, lat2, lon2) {
        const earthRadius = 6371000;
        const toRad = Math.PI / 180;
        const dLat = (lat2 - lat1) * toRad;
        const dLon = (lon2 - lon1) * toRad;
        const a = Math.sin(dLat / 2) ** 2
            + Math.cos(lat1 * toRad) * Math.cos(lat2 * toRad) * Math.sin(dLon / 2) ** 2;
        return 2 * earthRadius * Math.asin(Math.sqrt(a));
    }

    function destinationPoint(lat, lon, bearingDeg, distanceM) {
        const earthRadius = 6371000;
        const toRad = Math.PI / 180;
        const toDeg = 180 / Math.PI;
        const bearing = bearingDeg * toRad;
        const angularDistance = distanceM / earthRadius;
        const startLat = lat * toRad;
        const startLon = lon * toRad;

        const destLat = Math.asin(
            Math.sin(startLat) * Math.cos(angularDistance)
            + Math.cos(startLat) * Math.sin(angularDistance) * Math.cos(bearing)
        );
        const destLon = startLon + Math.atan2(
            Math.sin(bearing) * Math.sin(angularDistance) * Math.cos(startLat),
            Math.cos(angularDistance) - Math.sin(startLat) * Math.sin(destLat)
        );

        return [destLat * toDeg, destLon * toDeg];
    }

    function toNumber(value) {
        const parsed = Number(value);
        return Number.isFinite(parsed) ? parsed : null;
    }

    function toLatLng(item, latKey, lonKey) {
        if (!item) {
            return null;
        }
        const lat = toNumber(item[latKey]);
        const lon = toNumber(item[lonKey]);
        if (lat === null || lon === null) {
            return null;
        }
        return [lat, lon];
    }

    function fieldLayerEffects(item) {
        return Array.isArray(item && item.field_layer_effects) ? item.field_layer_effects : [];
    }

    function fieldLayerEffectRank(effect) {
        return FIELD_LAYER_EFFECT_RANK[String(effect && effect.severity ? effect.severity : "").toLowerCase()] || 0;
    }

    function topFieldLayerEffect(item) {
        return fieldLayerEffects(item)
            .slice()
            .sort((left, right) => fieldLayerEffectRank(right) - fieldLayerEffectRank(left))[0] || null;
    }

    function fieldLayerEffectColor(item) {
        const effect = topFieldLayerEffect(item);
        const severity = String(effect && effect.severity ? effect.severity : "").toLowerCase();
        return FIELD_LAYER_EFFECT_COLORS[severity] || ROLE_COLORS.hostile;
    }

    function fieldLayerEffectTooltip(item) {
        const effects = fieldLayerEffects(item);
        if (!effects.length) {
            return "";
        }
        return effects.map((effect) => `${effect.label}: ${effect.layer_name}`).join(" / ");
    }

    function buildRenderState(state) {
        return {
            tracks: Array.isArray(state.tracks) ? state.tracks : [],
            detections: Array.isArray(state.detections) ? state.detections : [],
            stations: Array.isArray(state.stations) ? state.stations : [],
            tasks: Array.isArray(state.tasks) ? state.tasks : [],
            fieldLayers: Array.isArray(state.fieldLayers) ? state.fieldLayers : [],
            aircraft: Array.isArray(state.aircraft) ? state.aircraft : [],
            playbackPoints: Array.isArray(state.playbackPoints) ? state.playbackPoints : [],
            playbackTracks: Array.isArray(state.playbackTracks) ? state.playbackTracks : [],
            replayCursor: state.replayCursor || null,
            replayEvents: Array.isArray(state.replayEvents) ? state.replayEvents : [],
            draftTarget: state.draftTarget || null,
            draftFieldLayer: state.draftFieldLayer || null,
            focus: state.focus || {}
        };
    }

    function findTrack(tracks, droneUid) {
        return tracks.find((item) => item.drone_uid === droneUid) || null;
    }

    function findStation(stations, stationId) {
        return stations.find((item) => item.id === stationId) || null;
    }

    function getLayerMeta(layerId) {
        return OFFLINE_LAYERS.find((item) => item.id === layerId) || OFFLINE_LAYERS.find((item) => item.id === DEFAULT_LAYER_ID);
    }

    function geoJsonPolygonPoints(layer) {
        const rings = layer && layer.geometry && Array.isArray(layer.geometry.coordinates)
            ? layer.geometry.coordinates
            : [];
        const outer = Array.isArray(rings[0]) ? rings[0] : [];
        return outer
            .map((point) => {
                if (!Array.isArray(point) || point.length < 2) {
                    return null;
                }
                const lon = toNumber(point[0]);
                const lat = toNumber(point[1]);
                return lat === null || lon === null ? null : [lat, lon];
            })
            .filter(Boolean);
    }

    function fieldLayerStyle(layer, focused) {
        const style = layer && layer.style && typeof layer.style === "object" ? layer.style : {};
        const rawColor = typeof style.color === "string" ? style.color : "";
        const layerType = layer && layer.layer_type;
        const color = layerType === "custom" && /^#[0-9a-f]{6}$/i.test(rawColor)
            ? rawColor
            : FIELD_LAYER_COLORS[layerType] || FIELD_LAYER_COLORS.custom;
        return {
            color,
            weight: focused ? 3 : 2,
            opacity: focused ? 0.9 : 0.72,
            fillColor: color,
            fillOpacity: Number.isFinite(Number(style.fillOpacity)) ? Number(style.fillOpacity) : 0.13,
            dashArray: layer.layer_type === "safe_corridor" ? "12 8" : layer.layer_type === "patrol_area" ? "4 7" : null
        };
    }

    function cleanFieldLayerDraftPoints(points) {
        if (!Array.isArray(points)) {
            return [];
        }
        return points
            .map((point) => Array.isArray(point) && point.length >= 2 ? [toNumber(point[0]), toNumber(point[1])] : null)
            .filter((point) => point && point[0] !== null && point[1] !== null);
    }

    function normalizeFieldLayerBounds(bounds) {
        if (!bounds) {
            return null;
        }
        const north = Math.max(Number(bounds.north), Number(bounds.south));
        const south = Math.min(Number(bounds.north), Number(bounds.south));
        const east = Math.max(Number(bounds.east), Number(bounds.west));
        const west = Math.min(Number(bounds.east), Number(bounds.west));
        if (![north, south, east, west].every(Number.isFinite) || north === south || east === west) {
            return null;
        }
        return { north, south, east, west };
    }

    function fieldLayerBoundsToPoints(bounds) {
        const normalized = normalizeFieldLayerBounds(bounds);
        if (!normalized) {
            return [];
        }
        return [
            [normalized.north, normalized.west],
            [normalized.north, normalized.east],
            [normalized.south, normalized.east],
            [normalized.south, normalized.west]
        ];
    }

    function fieldLayerDraftBounds(points) {
        const cleanPoints = cleanFieldLayerDraftPoints(points);
        if (cleanPoints.length < 2) {
            return null;
        }
        const lats = cleanPoints.map((point) => point[0]);
        const lons = cleanPoints.map((point) => point[1]);
        return normalizeFieldLayerBounds({
            north: Math.max(...lats),
            south: Math.min(...lats),
            east: Math.max(...lons),
            west: Math.min(...lons)
        });
    }

    function fieldLayerBoundsFromLatLngs(start, end) {
        if (!start || !end) {
            return null;
        }
        return normalizeFieldLayerBounds({
            north: start.lat,
            south: end.lat,
            east: end.lng,
            west: start.lng
        });
    }

    function fieldLayerBoundsFromHandle(bounds, handleId, latlng) {
        if (!bounds || !latlng) {
            return null;
        }
        const next = { ...bounds };
        if (handleId.includes("n")) {
            next.north = latlng.lat;
        }
        if (handleId.includes("s")) {
            next.south = latlng.lat;
        }
        if (handleId.includes("e")) {
            next.east = latlng.lng;
        }
        if (handleId.includes("w")) {
            next.west = latlng.lng;
        }
        return normalizeFieldLayerBounds(next);
    }

    function fieldLayerHandlePositions(points) {
        const bounds = fieldLayerDraftBounds(points);
        if (!bounds) {
            return [];
        }
        const midLat = (bounds.north + bounds.south) / 2;
        const midLon = (bounds.east + bounds.west) / 2;
        return [
            { id: "nw", point: [bounds.north, bounds.west] },
            { id: "n", point: [bounds.north, midLon] },
            { id: "ne", point: [bounds.north, bounds.east] },
            { id: "e", point: [midLat, bounds.east] },
            { id: "se", point: [bounds.south, bounds.east] },
            { id: "s", point: [bounds.south, midLon] },
            { id: "sw", point: [bounds.south, bounds.west] },
            { id: "w", point: [midLat, bounds.west] }
        ];
    }

    function createFieldLayerHandleIcon(handleId) {
        return L.divIcon({
            className: `field-layer-resize-handle field-layer-resize-handle-${handleId}`,
            html: "<span></span>",
            iconSize: [18, 18],
            iconAnchor: [9, 9]
        });
    }

    function isPrimaryMouseButton(event) {
        return event && (event.button === 0 || event.which === 1);
    }

    function isSecondaryMouseButton(event) {
        return event && (event.button === 2 || event.which === 3);
    }

    function layerUrl(layerId) {
        return `/ui/static/maps/tiles/${layerId}/{z}/{x}/{y}.png`;
    }

    function escapeHtml(value) {
        return String(value || "").replace(/[&<>"']/g, (char) => ({
            "&": "&amp;",
            "<": "&lt;",
            ">": "&gt;",
            "\"": "&quot;",
            "'": "&#39;"
        })[char]);
    }

    function buildTooltip(text) {
        return {
            content: escapeHtml(text),
            options: {
                className: "map-tooltip",
                direction: "top",
                offset: [0, -10]
            }
        };
    }

    function parseMapConfig(container) {
        if (!container || !container.dataset.mapConfig) {
            return {};
        }
        try {
            return JSON.parse(container.dataset.mapConfig);
        } catch (_error) {
            return {};
        }
    }

    function configNumber(config, key, fallback) {
        const parsed = Number(config[key]);
        return Number.isFinite(parsed) ? parsed : fallback;
    }

    function configCenter(config, fallback) {
        if (!Array.isArray(config.home_center) || config.home_center.length !== 2) {
            return fallback;
        }
        const lat = Number(config.home_center[0]);
        const lon = Number(config.home_center[1]);
        return Number.isFinite(lat) && Number.isFinite(lon) ? [lat, lon] : fallback;
    }

    function textFieldUsesName(textField) {
        try {
            return JSON.stringify(textField).includes("name");
        } catch (_error) {
            return false;
        }
    }

    function localizedNameExpression(language) {
        const cleanLanguage = String(language || "tr").trim() || "tr";
        return [
            "coalesce",
            ["get", `name:${cleanLanguage}`],
            ["get", `name_${cleanLanguage}`],
            ["get", "name:tr"],
            ["get", "name_tr"],
            ["get", "name:latin"],
            ["get", "name_en"],
            ["get", "name"],
            ""
        ];
    }

    function normalizeHiddenMapLabels(labels) {
        const source = Array.isArray(labels) ? labels : [];
        return [...new Set(source
            .map((label) => String(label || "").trim().toLocaleLowerCase("tr-TR"))
            .filter(Boolean))];
    }

    function hideConfiguredMapLabelsExpression(nameExpression, labels) {
        const hiddenLabels = normalizeHiddenMapLabels(labels);
        if (!hiddenLabels.length) {
            return nameExpression;
        }
        const visibleName = ["downcase", nameExpression];
        const checks = hiddenLabels.map((label) => [">=", ["index-of", label, visibleName], 0]);
        return ["case", ["any", ...checks], "", nameExpression];
    }

    function localizeMapLibreStyle(style, language, hiddenLabels) {
        const clonedStyle = JSON.parse(JSON.stringify(style));
        if (!Array.isArray(clonedStyle.layers)) {
            return clonedStyle;
        }
        const nameExpression = localizedNameExpression(language);
        const visibleNameExpression = hideConfiguredMapLabelsExpression(nameExpression, hiddenLabels);
        clonedStyle.layers.forEach((layer) => {
            if (!layer || layer.type !== "symbol" || !layer.layout || !layer.layout["text-field"]) {
                return;
            }
            if (textFieldUsesName(layer.layout["text-field"])) {
                layer.layout["text-field"] = visibleNameExpression;
            }
        });
        return clonedStyle;
    }

    function createHostileIcon(focused) {
        return L.divIcon({
            className: "hostile-map-icon-shell",
            html: `<span class="hostile-map-icon ${focused ? "is-focused" : ""}"><span class="hostile-map-icon-core"></span></span>`,
            iconSize: [28, 28],
            iconAnchor: [14, 14]
        });
    }

    function createStationIcon(focused) {
        return L.divIcon({
            className: "station-map-icon-shell",
            html: `<span class="station-map-icon ${focused ? "is-focused" : ""}"></span>`,
            iconSize: [18, 18],
            iconAnchor: [9, 9]
        });
    }

    function createAircraftIcon(headingDeg) {
        const heading = Number.isFinite(headingDeg) ? headingDeg : 0;
        return L.divIcon({
            className: "aircraft-map-icon-shell",
            html: `
                <span class="aircraft-map-icon" style="--aircraft-heading: ${heading}deg">
                    <svg class="aircraft-map-svg" viewBox="0 0 32 32" aria-hidden="true" focusable="false">
                        <path class="aircraft-map-shape" d="M16 2.2c1 0 1.7.8 1.7 1.9v9.3l11.4 5.8v2.5l-11.4-3.1v5.6l4.4 2.8v1.9L16 27.5l-6.1 1.4V27l4.4-2.8v-5.6L2.9 21.7v-2.5l11.4-5.8V4.1c0-1.1.7-1.9 1.7-1.9Z"></path>
                    </svg>
                </span>
            `,
            iconSize: [28, 28],
            iconAnchor: [14, 14]
        });
    }

    function createDraftTargetIcon() {
        return L.divIcon({
            className: "draft-target-map-icon-shell",
            html: '<span class="draft-target-map-icon"><span class="draft-target-map-icon-core"></span></span>',
            iconSize: [34, 34],
            iconAnchor: [17, 17]
        });
    }

    function focusKeyFromState(state) {
        return `${state.focus.taskId || ""}:${state.focus.detectionId || ""}:${state.focus.fieldLayerId || ""}`;
    }

    function createStatusControl() {
        const control = L.control({ position: "topright" });
        control.onAdd = function onAdd() {
            const node = L.DomUtil.create("div", "map-status-control");
            node.textContent = "Otomatik detay";
            return node;
        };
        control.setText = function setText(text, tone) {
            if (!this._container) {
                return;
            }
            this._container.textContent = text;
            this._container.dataset.tone = tone;
        };
        return control;
    }

    function layerContainsPoints(layer, points) {
        if (!points.length) {
            return true;
        }
        const bounds = L.latLngBounds(layer.bounds);
        return points.every((point) => bounds.contains(point));
    }

    function layerContainsPoint(layer, point) {
        if (!point) {
            return false;
        }
        return L.latLngBounds(layer.bounds).contains(point);
    }

    function collectRelevantPoints(state) {
        const points = [];
        const focusTask = state.tasks.find((item) => item.id === state.focus.taskId) || null;
        const focusDetection = state.detections.find((item) => item.id === state.focus.detectionId) || null;
        const focusFieldLayer = state.fieldLayers.find((item) => item.id === state.focus.fieldLayerId) || null;

        if (focusFieldLayer) {
            geoJsonPolygonPoints(focusFieldLayer).forEach((point) => points.push(point));
            return points;
        }

        if (focusTask) {
            const target = toLatLng(focusTask, "target_lat", "target_lon");
            const station = findStation(state.stations, focusTask.operator_station_id);
            const interceptorTrack = findTrack(state.tracks, focusTask.interceptor_drone_uid);
            const reconTrack = findTrack(state.tracks, focusTask.recon_drone_uid);
            [target, toLatLng(station, "lat", "lon"), toLatLng(interceptorTrack, "lat", "lon"), toLatLng(reconTrack, "lat", "lon")]
                .filter(Boolean)
                .forEach((item) => points.push(item));
            state.playbackPoints.forEach((item) => {
                const point = toLatLng(item, "lat", "lon");
                if (point) {
                    points.push(point);
                }
            });
            state.playbackTracks.forEach((track) => {
                const trackPoints = Array.isArray(track.points) ? track.points : [];
                trackPoints.forEach((item) => {
                    const point = toLatLng(item, "lat", "lon");
                    if (point) {
                        points.push(point);
                    }
                });
            });
            return points;
        }

        if (focusDetection) {
            const target = toLatLng(focusDetection, "target_lat", "target_lon");
            const reconTrack = findTrack(state.tracks, focusDetection.recon_drone_uid);
            const linkedTask = state.tasks.find((item) => item.hostile_detection_id === focusDetection.id) || null;
            const station = linkedTask ? findStation(state.stations, linkedTask.operator_station_id) : null;
            const interceptorTrack = linkedTask ? findTrack(state.tracks, linkedTask.interceptor_drone_uid) : null;
            [target, toLatLng(reconTrack, "lat", "lon"), toLatLng(station, "lat", "lon"), toLatLng(interceptorTrack, "lat", "lon")]
                .filter(Boolean)
                .forEach((item) => points.push(item));
            return points;
        }

        state.tracks.forEach((item) => {
            const point = toLatLng(item, "lat", "lon");
            if (point) {
                points.push(point);
            }
        });
        state.stations.forEach((item) => {
            const point = toLatLng(item, "lat", "lon");
            if (point) {
                points.push(point);
            }
        });
        state.detections.forEach((item) => {
            const point = toLatLng(item, "target_lat", "target_lon");
            if (point) {
                points.push(point);
            }
        });
        state.fieldLayers.forEach((item) => {
            geoJsonPolygonPoints(item).forEach((point) => points.push(point));
        });
        state.playbackPoints.forEach((item) => {
            const point = toLatLng(item, "lat", "lon");
            if (point) {
                points.push(point);
            }
        });
        state.playbackTracks.forEach((track) => {
            const trackPoints = Array.isArray(track.points) ? track.points : [];
            trackPoints.forEach((item) => {
                const point = toLatLng(item, "lat", "lon");
                if (point) {
                    points.push(point);
                }
            });
        });
        return points;
    }

    function suggestLayerId(state) {
        const points = collectRelevantPoints(state);
        const orderedLayers = [...OFFLINE_LAYERS].reverse();
        const match = orderedLayers.find((layer) => layerContainsPoints(layer, points));
        return match ? match.id : "world";
    }

    function chooseLayerForViewport(center, zoom) {
        const candidates = OFFLINE_LAYERS.filter((layer) => layerContainsPoint(layer, center));
        if (!candidates.length) {
            return getLayerMeta("world");
        }

        const eligible = candidates
            .filter((layer) => zoom >= layer.minZoom)
            .sort((left, right) => right.minZoom - left.minZoom);
        if (eligible.length) {
            return eligible[0];
        }

        return candidates.sort((left, right) => left.minZoom - right.minZoom)[0];
    }

    function createMap(options) {
        const container = document.getElementById(options.canvasId || options.containerId);
        if (!container) {
            return null;
        }
        const mapConfig = parseMapConfig(container);

        if (!window.L) {
            container.innerHTML = `<div class="map-fallback-message">${options.emptyMessage || "Offline harita kütüphanesi yüklenemedi."}</div>`;
            return noopMapController();
        }

        let useVectorBasemap = Boolean(mapConfig.use_vector_basemap && window.maplibregl && L.maplibreGL);
        const vectorMinZoom = configNumber(mapConfig, "min_zoom", GLOBAL_MIN_ZOOM);
        const vectorMaxZoom = configNumber(mapConfig, "max_zoom", 19);
        const vectorHomeCenter = configCenter(mapConfig, getLayerMeta(DEFAULT_LAYER_ID).homeCenter);
        const vectorHomeZoom = configNumber(mapConfig, "home_zoom", getLayerMeta(DEFAULT_LAYER_ID).homeZoom);
        const initialLayer = useVectorBasemap
            ? {
                id: "global-vector",
                label: "Dünya",
                homeCenter: vectorHomeCenter,
                homeZoom: vectorHomeZoom,
                minZoom: vectorMinZoom,
                maxZoom: vectorMaxZoom,
                maxNativeZoom: vectorMaxZoom
            }
            : getLayerMeta(DEFAULT_LAYER_ID);
        const mapOptions = {
            zoomControl: true,
            attributionControl: true,
            preferCanvas: true,
            minZoom: useVectorBasemap ? vectorMinZoom : GLOBAL_MIN_ZOOM,
            maxZoom: useVectorBasemap ? vectorMaxZoom : GLOBAL_MAX_ZOOM
        };
        if (!useVectorBasemap) {
            mapOptions.maxBounds = L.latLngBounds(GLOBAL_LAYER_BOUNDS).pad(0.01);
            mapOptions.maxBoundsViscosity = 0.8;
        }
        const map = L.map(container, mapOptions);
        map.attributionControl.setPrefix("");

        const statusControl = createStatusControl();
        statusControl.addTo(map);

        let activeLayerId = initialLayer.id;
        let hasInitialView = false;
        let lastFocusKey = "";
        let targetPickingEnabled = false;
        let fieldLayerDrawingEnabled = false;
        let currentDraftFieldLayerPoints = [];
        let currentDraftFieldLayerStyle = {};
        let fieldLayerSelection = null;
        let fieldLayerResize = null;
        let fieldLayerRightPan = null;
        let vectorLayerReady = false;
        const baseLayers = new Map();
        const mountedLayerIds = new Set();
        const fieldLayerHandleMarkers = new Map();

        const layers = {
            airTraffic: L.layerGroup().addTo(map),
            fieldLayers: L.layerGroup().addTo(map),
            draftTarget: L.layerGroup().addTo(map),
            draftFieldLayer: L.layerGroup().addTo(map),
            draftFieldLayerHandles: L.layerGroup().addTo(map),
            taskRoutes: L.layerGroup().addTo(map),
            playback: L.layerGroup().addTo(map),
            stations: L.layerGroup().addTo(map),
            detections: L.layerGroup().addTo(map),
            tracks: L.layerGroup().addTo(map),
            focus: L.layerGroup().addTo(map)
        };

        function notifyFieldLayerDraftChange(points, source) {
            const cleanPoints = cleanFieldLayerDraftPoints(points).slice(0, 4);
            currentDraftFieldLayerPoints = cleanPoints;
            if (typeof options.onFieldLayerDraftChange === "function") {
                options.onFieldLayerDraftChange({
                    points: cleanPoints.map((point) => [...point]),
                    source
                });
            }
        }

        function draftFieldLayerColor() {
            const style = currentDraftFieldLayerStyle && typeof currentDraftFieldLayerStyle === "object"
                ? currentDraftFieldLayerStyle
                : {};
            const color = typeof style.color === "string" ? style.color : "";
            return style.layer_type === "custom" && /^#[0-9a-f]{6}$/i.test(color)
                ? color
                : FIELD_LAYER_COLORS[style.layer_type] || FIELD_LAYER_COLORS.custom;
        }

        function renderDraftFieldLayerShape(points) {
            layers.draftFieldLayer.clearLayers();
            const cleanPoints = cleanFieldLayerDraftPoints(points).slice(0, 4);
            if (cleanPoints.length !== 4) {
                return;
            }
            const color = draftFieldLayerColor();
            L.polygon(cleanPoints.concat([cleanPoints[0]]), {
                className: "field-layer-draft-polygon",
                color,
                weight: 2,
                opacity: 0.96,
                fillColor: color,
                fillOpacity: 0.16,
                dashArray: "10 6",
                interactive: false
            }).addTo(layers.draftFieldLayer);
        }

        function syncFieldLayerHandleMarkers(points) {
            const positions = fieldLayerHandlePositions(points);
            positions.forEach((handle) => {
                const marker = fieldLayerHandleMarkers.get(handle.id);
                if (marker) {
                    marker.setLatLng(handle.point);
                }
            });
        }

        function handleFieldLayerResizeDrag(event) {
            if (!fieldLayerResize || !fieldLayerResize.baseBounds) {
                return;
            }
            const bounds = fieldLayerBoundsFromHandle(
                fieldLayerResize.baseBounds,
                fieldLayerResize.handleId,
                event.target.getLatLng()
            );
            const points = fieldLayerBoundsToPoints(bounds);
            if (points.length !== 4) {
                return;
            }
            currentDraftFieldLayerPoints = points;
            fieldLayerResize.lastPoints = points;
            renderDraftFieldLayerShape(points);
            syncFieldLayerHandleMarkers(points);
        }

        function handleFieldLayerResizeEnd() {
            const points = fieldLayerResize && fieldLayerResize.lastPoints
                ? fieldLayerResize.lastPoints
                : currentDraftFieldLayerPoints;
            fieldLayerResize = null;
            container.classList.remove("is-field-layer-resizing");
            cleanupFieldLayerRightPan();
            if (cleanFieldLayerDraftPoints(points).length === 4) {
                notifyFieldLayerDraftChange(points, "resize");
            }
        }

        function renderDraftFieldLayerHandles(points) {
            layers.draftFieldLayerHandles.clearLayers();
            fieldLayerHandleMarkers.clear();
            const cleanPoints = cleanFieldLayerDraftPoints(points).slice(0, 4);
            if (cleanPoints.length !== 4) {
                return;
            }
            fieldLayerHandlePositions(cleanPoints).forEach((handle) => {
                const marker = L.marker(handle.point, {
                    icon: createFieldLayerHandleIcon(handle.id),
                    draggable: true,
                    keyboard: false,
                    zIndexOffset: 560
                }).addTo(layers.draftFieldLayerHandles);
                marker.on("dragstart", () => {
                    cleanupFieldLayerRightPan();
                    fieldLayerResize = {
                        handleId: handle.id,
                        baseBounds: fieldLayerDraftBounds(currentDraftFieldLayerPoints),
                        lastPoints: currentDraftFieldLayerPoints
                    };
                    container.classList.add("is-field-layer-resizing");
                });
                marker.on("drag", handleFieldLayerResizeDrag);
                marker.on("dragend", handleFieldLayerResizeEnd);
                fieldLayerHandleMarkers.set(handle.id, marker);
            });
        }

        function cleanupFieldLayerSelection() {
            L.DomEvent.off(document, "mousemove", handleFieldLayerSelectionMove);
            L.DomEvent.off(document, "mouseup", handleFieldLayerSelectionEnd);
            container.classList.remove("is-field-layer-selecting");
            cleanupFieldLayerRightPan();
        }

        function cleanupFieldLayerRightPan() {
            L.DomEvent.off(document, "mousemove", handleFieldLayerRightPanMove);
            L.DomEvent.off(document, "mouseup", handleFieldLayerRightPanEnd);
            fieldLayerRightPan = null;
            container.classList.remove("is-field-layer-panning");
        }

        function handleFieldLayerRightPanMove(event) {
            if (!fieldLayerRightPan) {
                return;
            }
            const point = map.mouseEventToContainerPoint(event);
            const previousPoint = fieldLayerRightPan.previousPoint;
            const deltaX = previousPoint.x - point.x;
            const deltaY = previousPoint.y - point.y;
            if (deltaX !== 0 || deltaY !== 0) {
                fieldLayerRightPan.previousPoint = point;
                fieldLayerRightPan.moved = true;
                map.panBy([deltaX, deltaY], { animate: false });
            }
            L.DomEvent.preventDefault(event);
            L.DomEvent.stopPropagation(event);
        }

        function handleFieldLayerRightPanEnd(event) {
            if (!fieldLayerRightPan) {
                return;
            }
            cleanupFieldLayerRightPan();
            L.DomEvent.preventDefault(event);
            L.DomEvent.stopPropagation(event);
        }

        function startFieldLayerRightPan(event) {
            if (!fieldLayerDrawingEnabled || targetPickingEnabled || fieldLayerResize || fieldLayerSelection) {
                return false;
            }
            const original = event.originalEvent || event;
            if (!isSecondaryMouseButton(original)) {
                return false;
            }
            fieldLayerRightPan = {
                previousPoint: map.mouseEventToContainerPoint(original),
                moved: false
            };
            container.classList.add("is-field-layer-panning");
            L.DomEvent.on(document, "mousemove", handleFieldLayerRightPanMove);
            L.DomEvent.on(document, "mouseup", handleFieldLayerRightPanEnd);
            L.DomEvent.preventDefault(original);
            L.DomEvent.stopPropagation(original);
            return true;
        }

        function preventMapContextMenu(event) {
            const original = event.originalEvent || event;
            L.DomEvent.preventDefault(original);
            L.DomEvent.stopPropagation(original);
        }

        function handleFieldLayerSelectionMove(event) {
            if (!fieldLayerSelection) {
                return;
            }
            const point = map.mouseEventToContainerPoint(event);
            if (!fieldLayerSelection.moved && point.distanceTo(fieldLayerSelection.startPoint) < 6) {
                return;
            }
            fieldLayerSelection.moved = true;
            const bounds = fieldLayerBoundsFromLatLngs(
                fieldLayerSelection.startLatLng,
                map.mouseEventToLatLng(event)
            );
            const points = fieldLayerBoundsToPoints(bounds);
            if (points.length !== 4) {
                return;
            }
            currentDraftFieldLayerPoints = points;
            renderDraftFieldLayerShape(points);
            layers.draftFieldLayerHandles.clearLayers();
            fieldLayerHandleMarkers.clear();
            L.DomEvent.preventDefault(event);
        }

        function handleFieldLayerSelectionEnd(event) {
            if (!fieldLayerSelection) {
                return;
            }
            const selection = fieldLayerSelection;
            fieldLayerSelection = null;
            cleanupFieldLayerSelection();
            if (selection.moved && currentDraftFieldLayerPoints.length === 4) {
                notifyFieldLayerDraftChange(currentDraftFieldLayerPoints, "selection");
                renderDraftFieldLayerHandles(currentDraftFieldLayerPoints);
            } else {
                currentDraftFieldLayerPoints = selection.previousPoints;
                renderDraftFieldLayerShape(currentDraftFieldLayerPoints);
                renderDraftFieldLayerHandles(currentDraftFieldLayerPoints);
            }
            L.DomEvent.preventDefault(event);
        }

        function startFieldLayerSelection(event) {
            if (!fieldLayerDrawingEnabled || targetPickingEnabled || fieldLayerResize) {
                return;
            }
            if (fieldLayerRightPan) {
                return;
            }
            const original = event.originalEvent;
            if (!isPrimaryMouseButton(original)) {
                return;
            }
            if (original.target && original.target.closest && original.target.closest(".field-layer-resize-handle")) {
                return;
            }
            fieldLayerSelection = {
                startLatLng: event.latlng,
                startPoint: map.mouseEventToContainerPoint(original),
                previousPoints: currentDraftFieldLayerPoints.map((point) => [...point]),
                moved: false
            };
            container.classList.add("is-field-layer-selecting");
            L.DomEvent.on(document, "mousemove", handleFieldLayerSelectionMove);
            L.DomEvent.on(document, "mouseup", handleFieldLayerSelectionEnd);
            L.DomEvent.preventDefault(original);
            L.DomEvent.stopPropagation(original);
        }

        function startFieldLayerInteraction(event) {
            startFieldLayerSelection(event);
        }

        async function addVectorBasemap() {
            const styleUrl = String(mapConfig.style_url || "").trim();
            if (!styleUrl) {
                useVectorBasemap = false;
                statusControl.setText("Küresel harita yapılandırması eksik", "error");
                syncBaseLayersToViewport();
                return;
            }

            statusControl.setText("Küresel harita / Türkçe etiketler yükleniyor", "");
            let style = styleUrl;
            let localizedStyle = false;
            try {
                const response = await fetch(styleUrl, { credentials: "omit" });
                if (!response.ok) {
                    throw new Error(String(response.status));
                }
                style = localizeMapLibreStyle(
                    await response.json(),
                    mapConfig.label_language || "tr",
                    mapConfig.hidden_labels
                );
                localizedStyle = true;
            } catch (_error) {
                style = styleUrl;
            }

            try {
                L.maplibreGL({
                    style,
                    interactive: false,
                    attributionControl: false
                }).addTo(map);
                vectorLayerReady = true;
                statusControl.setText(localizedStyle ? "Küresel harita / Türkçe etiket öncelikli" : "Küresel harita", "ok");
            } catch (_error) {
                useVectorBasemap = false;
                vectorLayerReady = false;
                statusControl.setText("Küresel harita yüklenemedi / offline katman", "error");
                syncBaseLayersToViewport();
            }
        }

        function ensureBaseLayer(layer) {
            if (baseLayers.has(layer.id)) {
                return baseLayers.get(layer.id);
            }

            const stats = { loaded: 0, failed: 0 };
            const tileLayer = L.tileLayer(layerUrl(layer.id), {
                minZoom: layer.minZoom,
                maxZoom: GLOBAL_MAX_ZOOM,
                maxNativeZoom: layer.maxNativeZoom,
                noWrap: true,
                bounds: layer.bounds,
                zIndex: 10 + OFFLINE_LAYERS.findIndex((item) => item.id === layer.id),
                attribution: "&copy; OpenStreetMap contributors"
            });
            tileLayer.on("tileload", () => {
                stats.loaded += 1;
                if (activeLayerId === layer.id && stats.loaded > 0) {
                    statusControl.setText(`Otomatik detay / ${layer.label}`, "ok");
                }
            });
            tileLayer.on("tileerror", () => {
                stats.failed += 1;
                if (activeLayerId === layer.id && !stats.loaded && stats.failed > 4) {
                    statusControl.setText(`Otomatik detay / ${layer.label} eksik`, "error");
                }
            });
            const record = { layer, tileLayer, stats };
            baseLayers.set(layer.id, record);
            return record;
        }

        function layerChain(layerId) {
            const index = OFFLINE_LAYERS.findIndex((item) => item.id === layerId);
            if (index === -1) {
                return [OFFLINE_LAYERS[0]];
            }
            return OFFLINE_LAYERS.slice(0, index + 1);
        }

        function syncBaseLayersToViewport() {
            if (!map._loaded) {
                map.setView(initialLayer.homeCenter, initialLayer.homeZoom, { animate: false });
            }
            if (!map._loaded) {
                return;
            }
            if (useVectorBasemap) {
                activeLayerId = initialLayer.id;
                if (!vectorLayerReady) {
                    statusControl.setText("Küresel harita / Türkçe etiketler yükleniyor", "");
                }
                return;
            }

            const viewportLayer = chooseLayerForViewport(map.getCenter(), map.getZoom());
            activeLayerId = viewportLayer.id;
            const requiredLayers = layerChain(viewportLayer.id);
            const requiredIds = new Set(requiredLayers.map((item) => item.id));

            Array.from(mountedLayerIds).forEach((layerId) => {
                if (requiredIds.has(layerId)) {
                    return;
                }
                const record = baseLayers.get(layerId);
                if (record && map.hasLayer(record.tileLayer)) {
                    map.removeLayer(record.tileLayer);
                }
                mountedLayerIds.delete(layerId);
            });

            requiredLayers.forEach((layer) => {
                const record = ensureBaseLayer(layer);
                if (!map.hasLayer(record.tileLayer)) {
                    record.tileLayer.addTo(map);
                }
                mountedLayerIds.add(layer.id);
            });

            const activeRecord = ensureBaseLayer(viewportLayer);
            if (activeRecord.stats.loaded > 0) {
                statusControl.setText(`Otomatik detay / ${viewportLayer.label}`, "ok");
            } else if (activeRecord.stats.failed > 4) {
                statusControl.setText(`Otomatik detay / ${viewportLayer.label} eksik`, "error");
            } else {
                statusControl.setText(`Otomatik detay / ${viewportLayer.label} yükleniyor`, "");
            }
        }

        if (useVectorBasemap) {
            addVectorBasemap();
        }
        syncBaseLayersToViewport();

        map.on("moveend zoomend", () => {
            if (!hasInitialView) {
                return;
            }
            syncBaseLayersToViewport();
        });

        container.addEventListener("mousedown", startFieldLayerRightPan, true);
        container.addEventListener("contextmenu", preventMapContextMenu, true);
        map.on("mousedown", startFieldLayerInteraction);

        map.on("click", (event) => {
            if (targetPickingEnabled && typeof options.onMapClick === "function") {
                options.onMapClick({
                    lat: event.latlng.lat,
                    lon: event.latlng.lng
                });
            }
        });

        function clearLayers() {
            Object.values(layers).forEach((layer) => layer.clearLayers());
            fieldLayerHandleMarkers.clear();
        }

        function setTargetPickingEnabled(enabled) {
            targetPickingEnabled = Boolean(enabled);
            container.classList.toggle("is-target-picking", targetPickingEnabled);
        }

        function setFieldLayerDrawingEnabled(enabled) {
            fieldLayerDrawingEnabled = Boolean(enabled);
            container.classList.toggle("is-field-layer-drawing", fieldLayerDrawingEnabled);
            if (!fieldLayerDrawingEnabled && fieldLayerSelection) {
                const previousPoints = fieldLayerSelection.previousPoints;
                fieldLayerSelection = null;
                cleanupFieldLayerSelection();
                currentDraftFieldLayerPoints = previousPoints;
                renderDraftFieldLayerShape(currentDraftFieldLayerPoints);
                renderDraftFieldLayerHandles(currentDraftFieldLayerPoints);
            }
            if (!fieldLayerDrawingEnabled && fieldLayerRightPan) {
                cleanupFieldLayerRightPan();
            }
            if (map.dragging) {
                if (fieldLayerDrawingEnabled) {
                    map.dragging.disable();
                } else {
                    map.dragging.enable();
                }
            }
        }

        function fitToState(state) {
            const focusKey = focusKeyFromState(state);
            const points = collectRelevantPoints(state);
            const forceFit = !hasInitialView || options.fitOnEveryUpdate || focusKey !== lastFocusKey;
            if (!forceFit) {
                return;
            }

            const suggestedLayer = useVectorBasemap ? initialLayer : getLayerMeta(suggestLayerId(state));
            const maxAllowedZoom = useVectorBasemap ? vectorMaxZoom : GLOBAL_MAX_ZOOM;
            if (points.length === 1) {
                const focusZoom = Math.min(maxAllowedZoom, Math.max(suggestedLayer.homeZoom + 1, suggestedLayer.minZoom + 1));
                map.setView(points[0], focusZoom, { animate: false });
            } else if (points.length > 1) {
                map.fitBounds(L.latLngBounds(points).pad(0.22), {
                    animate: false,
                    padding: [26, 26],
                    maxZoom: suggestedLayer.maxZoom
                });
            } else {
                map.setView(initialLayer.homeCenter, initialLayer.homeZoom, { animate: false });
            }

            map.invalidateSize(false);
            hasInitialView = true;
            lastFocusKey = focusKey;
            syncBaseLayersToViewport();
        }

        function renderAirTraffic(state) {
            state.aircraft.forEach((aircraft) => {
                const point = toLatLng(aircraft, "lat", "lon");
                if (!point) {
                    return;
                }

                const heading = toNumber(aircraft.true_track_deg);
                const marker = L.marker(point, {
                    icon: createAircraftIcon(heading),
                    keyboard: false,
                    zIndexOffset: -120
                }).addTo(layers.airTraffic);

                const altitude = toNumber(aircraft.geo_altitude_m) ?? toNumber(aircraft.baro_altitude_m);
                const speed = toNumber(aircraft.velocity_mps);
                const labelParts = [
                    aircraft.callsign || aircraft.icao24 || "Sivil hava aracı",
                    altitude === null ? null : `${Math.round(altitude)} m`,
                    speed === null ? null : `${Math.round(speed)} m/s`
                ].filter(Boolean);
                const tooltip = buildTooltip(labelParts.join(" / "));
                marker.bindTooltip(tooltip.content, tooltip.options);

                // Direction is encoded by the rotating aircraft icon; no extra vector line keeps the civil layer clean.
            });
        }

        function renderDraftTarget(state) {
            const point = toLatLng(state.draftTarget, "lat", "lon");
            if (!point) {
                return;
            }

            L.marker(point, {
                icon: createDraftTargetIcon(),
                keyboard: false,
                zIndexOffset: 420
            }).addTo(layers.draftTarget);
            L.circle(point, {
                radius: 130,
                color: ROLE_COLORS.hostile,
                weight: 1.6,
                opacity: 0.72,
                fillOpacity: 0.04,
                dashArray: "6 6"
            }).addTo(layers.draftTarget);
        }

        function renderFieldLayers(state) {
            state.fieldLayers.forEach((layer) => {
                const points = geoJsonPolygonPoints(layer);
                if (points.length < 4) {
                    return;
                }
                const focused = state.focus.fieldLayerId === layer.id;
                const polygon = L.polygon(points, fieldLayerStyle(layer, focused)).addTo(layers.fieldLayers);
                polygon.bindTooltip(buildTooltip(layer.name || "Saha katmani").content, {
                    className: "map-tooltip",
                    sticky: true
                });
            });
        }

        function renderDraftFieldLayer(state) {
            const points = Array.isArray(state.draftFieldLayer && state.draftFieldLayer.points)
                ? state.draftFieldLayer.points
                : [];
            const style = state.draftFieldLayer && state.draftFieldLayer.style && typeof state.draftFieldLayer.style === "object"
                ? state.draftFieldLayer.style
                : {};
            currentDraftFieldLayerStyle = {
                ...style,
                layer_type: state.draftFieldLayer && state.draftFieldLayer.layer_type
            };
            currentDraftFieldLayerPoints = cleanFieldLayerDraftPoints(points).slice(0, 4);
            renderDraftFieldLayerShape(currentDraftFieldLayerPoints);
            renderDraftFieldLayerHandles(currentDraftFieldLayerPoints);
        }

        function renderPlayback(state) {
            const legacyPoints = state.playbackPoints
                .map((item) => toLatLng(item, "lat", "lon"))
                .filter(Boolean);
            if (legacyPoints.length > 1) {
                L.polyline(legacyPoints, {
                    color: "#f7c35f",
                    weight: 3,
                    opacity: 0.72,
                    dashArray: "8 8"
                }).addTo(layers.playback);
            }

            const cursorTime = state.replayCursor ? new Date(state.replayCursor).getTime() : null;
            state.playbackTracks.forEach((track) => {
                const roleKey = track.platform_role === "recon" ? "recon" : "interceptor";
                const color = ROLE_COLORS[roleKey] || "#f7c35f";
                const rawPoints = Array.isArray(track.points) ? track.points : [];
                const points = rawPoints.map((item) => toLatLng(item, "lat", "lon")).filter(Boolean);
                if (points.length > 1) {
                    L.polyline(points, {
                        color,
                        weight: roleKey === "recon" ? 2.5 : 3.2,
                        opacity: 0.78,
                        dashArray: roleKey === "recon" ? "5 7" : null
                    }).addTo(layers.playback);
                }
                if (cursorTime !== null && rawPoints.length) {
                    const cursorPoint = rawPoints
                        .filter((item) => new Date(item.timestamp).getTime() <= cursorTime)
                        .slice(-1)[0] || rawPoints[0];
                    const point = toLatLng(cursorPoint, "lat", "lon");
                    if (point) {
                        L.circleMarker(point, {
                            radius: 7,
                            color: "#f8fbf7",
                            weight: 2,
                            fillColor: color,
                            fillOpacity: 0.96
                        }).bindTooltip(
                            buildTooltip(`${track.drone_uid || "Playback"} / ${new Date(cursorPoint.timestamp).toLocaleTimeString("tr-TR")}`).content,
                            buildTooltip(`${track.drone_uid || "Playback"} / ${new Date(cursorPoint.timestamp).toLocaleTimeString("tr-TR")}`).options
                        ).addTo(layers.playback);
                    }
                }
            });

            state.replayEvents.forEach((event) => {
                const point = toLatLng(event, "lat", "lon");
                if (!point) {
                    return;
                }
                L.circleMarker(point, {
                    radius: 5.5,
                    color: "#f8fbf7",
                    weight: 1.4,
                    fillColor: "#f0cb4b",
                    fillOpacity: 0.95
                }).bindTooltip(buildTooltip(event.label || "Olay").content, buildTooltip(event.label || "Olay").options)
                    .addTo(layers.playback);
            });
        }

        function renderTaskRoutes(state) {
            state.tasks.forEach((task) => {
                if (!["pending", "accepted"].includes(task.status)) {
                    return;
                }
                const target = toLatLng(task, "target_lat", "target_lon");
                if (!target) {
                    return;
                }

                const focused = state.focus.taskId === task.id || state.focus.detectionId === task.hostile_detection_id;
                const station = findStation(state.stations, task.operator_station_id);
                const interceptorTrack = findTrack(state.tracks, task.interceptor_drone_uid);
                const reconTrack = findTrack(state.tracks, task.recon_drone_uid);
                const stationPoint = toLatLng(station, "lat", "lon");
                const interceptorPoint = toLatLng(interceptorTrack, "lat", "lon");
                const reconPoint = toLatLng(reconTrack, "lat", "lon");

                if (stationPoint) {
                L.polyline([stationPoint, target], {
                    color: focused ? ROLE_FOCUS_COLORS.station : ROLE_COLORS.station,
                    weight: focused ? 3.4 : 2.4,
                    opacity: 0.82,
                    dashArray: "10 8"
                }).addTo(layers.taskRoutes);
            }

            if (interceptorPoint) {
                L.polyline([interceptorPoint, target], {
                    color: focused ? ROLE_FOCUS_COLORS.interceptor : ROLE_COLORS.interceptor,
                    weight: focused ? 3.6 : 2.8,
                    opacity: 0.88
                }).addTo(layers.taskRoutes);
            }

            if (reconPoint) {
                L.polyline([reconPoint, target], {
                    color: focused ? ROLE_FOCUS_COLORS.recon : ROLE_COLORS.recon,
                    weight: focused ? 2.8 : 2,
                    opacity: 0.62,
                    dashArray: "4 7"
                }).addTo(layers.taskRoutes);
            }
            });
        }

        function renderStations(state) {
            state.stations.forEach((station) => {
                const point = toLatLng(station, "lat", "lon");
                if (!point) {
                    return;
                }
                const focused = state.focus.taskId
                    ? state.tasks.some((task) => task.id === state.focus.taskId && task.operator_station_id === station.id)
                    : state.focus.detectionId
                        ? state.detections.some((item) => item.id === state.focus.detectionId && item.assigned_operator_station_id === station.id)
                        : false;

                const marker = L.marker(point, {
                    icon: createStationIcon(focused),
                    keyboard: false
                }).addTo(layers.stations);
                const tooltip = buildTooltip(`${station.name} / ${station.assigned_interceptor_drone_uid || "Atanmamış"}`);
                marker.bindTooltip(tooltip.content, tooltip.options);
            });
        }

        function renderDetections(state) {
            state.detections.forEach((detection) => {
                if (["resolved", "cancelled"].includes(String(detection.status || "").toLowerCase())) {
                    return;
                }
                const target = toLatLng(detection, "target_lat", "target_lon");
                if (!target) {
                    return;
                }
                const reconTrack = findTrack(state.tracks, detection.recon_drone_uid);
                const reconPoint = toLatLng(reconTrack, "lat", "lon");
                const bearing = toNumber(detection.true_bearing_deg);
                const range = toNumber(detection.range_m);
                const effectColor = fieldLayerEffectColor(detection);
                const effectText = fieldLayerEffectTooltip(detection);
                if (reconPoint && bearing !== null && range !== null && range > 0) {
                    const left = destinationPoint(reconPoint[0], reconPoint[1], bearing - 14, range);
                    const right = destinationPoint(reconPoint[0], reconPoint[1], bearing + 14, range);
                    L.polygon([reconPoint, left, target, right], {
                        color: ROLE_COLORS.recon,
                        weight: 1.2,
                        opacity: 0.34,
                        fillColor: ROLE_COLORS.recon,
                        fillOpacity: 0.08,
                        dashArray: "5 7"
                    }).addTo(layers.detections);
                }

                L.circle(target, {
                    radius: 1000,
                    color: effectText ? effectColor : "#f0cb4b",
                    weight: 1.1,
                    opacity: 0.32,
                    fillOpacity: 0.015,
                    dashArray: "10 8"
                }).addTo(layers.detections);
                L.circle(target, {
                    radius: 500,
                    color: effectColor,
                    weight: 1.4,
                    opacity: 0.46,
                    fillOpacity: 0.035,
                    dashArray: "6 6"
                }).addTo(layers.detections);
                const marker = L.marker(target, {
                    icon: createHostileIcon(false),
                    keyboard: false,
                    zIndexOffset: 260
                }).addTo(layers.detections);
                const tooltip = buildTooltip(`${detection.contact_id} / ${Math.round(Number(detection.range_m || 0))} m${effectText ? ` / ${effectText}` : ""}`);
                marker.bindTooltip(tooltip.content, tooltip.options);

                L.circle(target, {
                    radius: 75,
                    color: effectColor,
                    weight: 1.4,
                    opacity: 0.5,
                    fillOpacity: 0.05
                }).addTo(layers.detections);
            });
        }

        function renderTracks(state) {
            state.tracks.forEach((track) => {
                const point = toLatLng(track, "lat", "lon");
                if (!point) {
                    return;
                }

                const focusedTask = state.tasks.find((task) => task.id === state.focus.taskId) || null;
                const focused = state.focus.taskId
                    ? focusedTask
                        ? [focusedTask.interceptor_drone_uid, focusedTask.recon_drone_uid].includes(track.drone_uid)
                        : false
                    : state.focus.detectionId
                        ? state.detections.some((item) => item.id === state.focus.detectionId && item.recon_drone_uid === track.drone_uid)
                        : false;

                const roleKey = track.platform_role === "recon" ? "recon" : "interceptor";
                const color = ROLE_COLORS[roleKey];
                const marker = L.circleMarker(point, {
                    radius: focused ? 8 : 6.5,
                    color: "#eef3ed",
                    weight: 2,
                    fillColor: color,
                    fillOpacity: 0.96
                }).addTo(layers.tracks);
                const tooltip = buildTooltip(`${track.drone_uid} / ${track.platform_role === "recon" ? "Keşif" : "Önleyici"}`);
                marker.bindTooltip(tooltip.content, tooltip.options);

                const heading = toNumber(track.heading_deg);
                if (heading !== null) {
                    const endPoint = destinationPoint(point[0], point[1], heading, 240);
                    L.polyline([point, endPoint], {
                        color,
                        weight: focused ? 3 : 2.2,
                        opacity: focused ? 0.88 : 0.58
                    }).addTo(layers.tracks);
                }
            });
        }

        function renderFocusHalo(state) {
            if (state.focus.taskId) {
                const task = state.tasks.find((item) => item.id === state.focus.taskId) || null;
                if (!task || !["pending", "accepted"].includes(task.status)) {
                    return;
                }
                const target = task ? toLatLng(task, "target_lat", "target_lon") : null;
                if (target) {
                    L.circle(target, {
                        radius: 160,
                        color: ROLE_FOCUS_COLORS.station,
                        weight: 1.8,
                        opacity: 0.85,
                        fillOpacity: 0
                    }).addTo(layers.focus);
                }
                return;
            }

            // Hostile targets intentionally keep a uniform map symbol; selection is shown in the side panels.
        }

        function render(nextState) {
            const state = buildRenderState(nextState);
            clearLayers();
            renderAirTraffic(state);
            renderFieldLayers(state);
            renderDraftTarget(state);
            renderDraftFieldLayer(state);
            renderPlayback(state);
            renderTaskRoutes(state);
            renderStations(state);
            renderDetections(state);
            renderTracks(state);
            renderFocusHalo(state);
            fitToState(state);
        }

        if (typeof ResizeObserver === "function") {
            const observer = new ResizeObserver(() => {
                map.invalidateSize(false);
            });
            observer.observe(container);
        }

        window.setTimeout(() => {
            map.invalidateSize(false);
            if (!hasInitialView) {
                syncBaseLayersToViewport();
            }
        }, 0);

        return {
            setState(nextState) {
                render(nextState || {});
            },
            setTargetPickingEnabled,
            setFieldLayerDrawingEnabled
        };
    }

    function noopMapController() {
        return {
            setState() {
                return undefined;
            },
            setTargetPickingEnabled() {
                return undefined;
            },
            setFieldLayerDrawingEnabled() {
                return undefined;
            }
        };
    }

    window.HavaMap = {
        createMap,
        distanceMeters
    };
})();
