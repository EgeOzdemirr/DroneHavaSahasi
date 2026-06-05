(function () {
    const root = document.querySelector('[data-page="control-center"]');
    if (!root) {
        return;
    }

    const csrfToken = document.body.dataset.csrfToken || "";
    const csrfCookieName = document.body.dataset.csrfCookieName || "fd_csrf_token";
    const readonly = root.dataset.readonly === "true";
    const flashNode = document.getElementById("flash-message");
    const tracksBody = document.getElementById("tracks-table-body");
    const detectionsList = document.getElementById("detections-list");
    const stationsList = document.getElementById("stations-list");
    const tasksList = document.getElementById("tasks-list");
    const stationForm = document.getElementById("station-form");
    const demoResetButton = document.getElementById("demo-reset-button");
    const demoResetResultNode = document.getElementById("demo-reset-result");
    const demoScenarioForm = document.getElementById("demo-scenario-form");
    const demoDetectionForm = document.getElementById("demo-detection-form");
    const demoCredentialsNode = document.getElementById("demo-credentials");
    const demoLastDetectionNode = document.getElementById("demo-last-detection");
    const demoOpenOperatorButton = document.getElementById("demo-open-operator");
    const mapSummaryNode = document.getElementById("control-map-summary");
    const mapFocusNode = document.getElementById("control-map-focus");
    const toggleMapTargetPickButton = document.getElementById("toggle-map-target-picker");
    const confirmMapTargetButton = document.getElementById("confirm-map-target");
    const cancelMapTargetButton = document.getElementById("cancel-map-target");
    const toggleAirTrafficButton = document.getElementById("toggle-air-traffic");
    const fieldLayersList = document.getElementById("field-layers-list");
    const fieldLayerForm = document.getElementById("field-layer-form");
    const fieldLayerNameInput = document.getElementById("field-layer-name");
    const fieldLayerTypeInput = document.getElementById("field-layer-type");
    const fieldLayerColorInput = document.getElementById("field-layer-color");
    const fieldLayerColorPalette = document.getElementById("field-layer-color-palette");
    const fieldLayerColorNote = document.getElementById("field-layer-color-note");
    const fieldLayerDrawStartButton = document.getElementById("field-layer-draw-start");
    const fieldLayerSaveButton = document.getElementById("field-layer-save");
    const fieldLayerCancelButton = document.getElementById("field-layer-cancel");
    const fieldLayerDraftStatus = document.getElementById("field-layer-draft-status");
    const replayTitle = document.getElementById("control-replay-title");
    const replayClock = document.getElementById("control-replay-clock");
    const replaySlider = document.getElementById("control-replay-slider");
    const replayPlayButton = document.getElementById("control-replay-play");
    const replaySpeedSelect = document.getElementById("control-replay-speed");
    const replayStatus = document.getElementById("control-replay-status");
    const progressPanel = document.getElementById("control-progress-panel");
    const taskTimeline = document.getElementById("task-timeline");
    const mapController = window.HavaMap ? window.HavaMap.createMap({
        canvasId: "control-map-canvas",
        emptyMessage: "Canlı operasyon verisi bekleniyor.",
        fitOnEveryUpdate: false,
        onMapClick: handleMapTargetClick,
        onFieldLayerDraftChange: handleFieldLayerDraftChange
    }) : null;

    let selectedDetectionId = null;
    let selectedTaskId = null;
    let selectedFieldLayerId = null;
    let latestState = {
        tracks: [],
        detections: [],
        stations: [],
        tasks: [],
        fieldLayers: [],
        aircraft: []
    };
    let airTrafficEnabled = false;
    let airTrafficLoading = false;
    let airTrafficLastError = "";
    let mapTargetPickEnabled = false;
    let mapTargetPickLoading = false;
    let draftMapTarget = null;
    let draftMapContactId = "";
    let mapCreatedTargets = [];
    let mapTargetSequence = 0;
    let fieldLayerDrawingEnabled = false;
    let draftFieldLayerPoints = [];
    let replayState = {
        taskId: null,
        tracks: [],
        events: [],
        minTime: null,
        maxTime: null,
        cursorTime: null,
        playing: false,
        timer: null
    };

    const ROLE_LABELS = {
        recon: "Keşif",
        interceptor: "Önleyici"
    };

    const STATUS_LABELS = {
        open: "Açık",
        assigned: "Atanmış",
        resolved: "İmha Edildi",
        pending: "Beklemede",
        accepted: "Kabul Edildi",
        completed: "Tamamlandı",
        rejected: "Reddedildi",
        cancelled: "İptal",
        expired: "Süre Doldu",
        active: "Aktif",
        inactive: "Pasif"
    };

    const FIELD_LAYER_LABELS = {
        base_perimeter: "Üs Çevresi",
        safe_corridor: "Güvenli Koridor",
        patrol_area: "Devriye Bölgesi",
        restricted_area: "Kısıtlı Bölge",
        custom: "Özel Katman"
    };
    const FIELD_LAYER_COLOR_OPTIONS = {
        base_perimeter: [
            { value: "#2d8cff", label: "Mavi" }
        ],
        safe_corridor: [
            { value: "#18c47f", label: "Yeşil" }
        ],
        patrol_area: [
            { value: "#f0cb4b", label: "Sarı" }
        ],
        restricted_area: [
            { value: "#ff1f2d", label: "Uyarı kırmızısı" }
        ],
        custom: [
            { value: "#a855f7", label: "Mor" }
        ]
    };
    const FIELD_LAYER_EFFECT_RANK = {
        critical: 4,
        high: 3,
        medium: 2,
        info: 1
    };
    const FIELD_LAYER_EFFECT_LABELS = {
        critical: "Kritik",
        high: "Yüksek",
        medium: "Orta",
        info: "Bilgi"
    };

    function showFlash(message, isError) {
        if (!flashNode) {
            return;
        }
        flashNode.hidden = false;
        flashNode.textContent = message;
        flashNode.classList.toggle("error-box", Boolean(isError));
        flashNode.classList.toggle("success-box", !isError);
    }

    function clearFlash() {
        if (!flashNode) {
            return;
        }
        flashNode.hidden = true;
        flashNode.textContent = "";
        flashNode.classList.remove("error-box", "success-box");
    }

    function readCookie(name) {
        const prefix = `${name}=`;
        const match = document.cookie.split("; ").find((item) => item.startsWith(prefix));
        return match ? decodeURIComponent(match.slice(prefix.length)) : "";
    }

    function currentCsrfToken() {
        return readCookie(csrfCookieName) || csrfToken;
    }

    async function fetchJson(url, options) {
        const method = options && options.method ? String(options.method).toUpperCase() : "GET";
        const response = await fetch(url, {
            credentials: "same-origin",
            headers: {
                Accept: "application/json",
                ...(method !== "GET"
                    ? { "Content-Type": "application/json", "X-CSRF-Token": currentCsrfToken() }
                    : {})
            },
            ...options
        });
        if (!response.ok) {
            let detail = `${response.status}`;
            try {
                const data = await response.json();
                detail = data.detail || detail;
            } catch (_error) {
                // ignore
            }
            throw new Error(detail);
        }
        return response.json();
    }

    function updateAirTrafficButton() {
        if (!toggleAirTrafficButton) {
            return;
        }
        toggleAirTrafficButton.setAttribute("aria-pressed", airTrafficEnabled ? "true" : "false");
        toggleAirTrafficButton.classList.toggle("is-active", airTrafficEnabled);
        toggleAirTrafficButton.classList.toggle("is-loading", airTrafficLoading);
        toggleAirTrafficButton.classList.toggle("has-error", Boolean(airTrafficLastError));
        if (!airTrafficEnabled) {
            toggleAirTrafficButton.textContent = "Sivil Hava Trafiğini Aktif Et";
            toggleAirTrafficButton.title = "OpenSky sivil hava trafiği katmanını aç";
            return;
        }
        if (airTrafficLoading) {
            toggleAirTrafficButton.textContent = "Sivil Trafik Yükleniyor";
            toggleAirTrafficButton.title = "OpenSky verisi alınıyor";
            return;
        }
        if (airTrafficLastError) {
            toggleAirTrafficButton.textContent = "Sivil Trafik Hatası";
            toggleAirTrafficButton.title = airTrafficLastError;
            return;
        }
        toggleAirTrafficButton.textContent = "Sivil Hava Trafiğini Kapat";
        toggleAirTrafficButton.title = `${latestState.aircraft.length} sivil hava aracı haritada gösteriliyor`;
    }

    async function refreshAirTraffic() {
        if (!airTrafficEnabled || airTrafficLoading) {
            return;
        }
        airTrafficLoading = true;
        airTrafficLastError = "";
        updateAirTrafficButton();
        try {
            latestState.aircraft = await fetchJson("/v1/air-traffic/opensky");
        } catch (error) {
            latestState.aircraft = [];
            airTrafficLastError = error.message || "Sivil trafik verisi alınamadı.";
        } finally {
            airTrafficLoading = false;
            updateAirTrafficButton();
            refreshMap();
        }
    }

    function updateMapTargetPickButton() {
        if (toggleMapTargetPickButton) {
            toggleMapTargetPickButton.setAttribute("aria-pressed", mapTargetPickEnabled ? "true" : "false");
            toggleMapTargetPickButton.classList.toggle("is-active", mapTargetPickEnabled);
            toggleMapTargetPickButton.classList.toggle("is-loading", mapTargetPickLoading);
        }
        if (toggleMapTargetPickButton) {
            if (mapTargetPickLoading) {
                toggleMapTargetPickButton.textContent = "Hedef Ekleniyor";
                toggleMapTargetPickButton.title = "Seçilen harita noktasında hedef tespiti oluşturuluyor";
            } else if (draftMapTarget) {
                toggleMapTargetPickButton.textContent = "Noktayı Değiştir";
                toggleMapTargetPickButton.title = "Seçili hedef noktasını değiştirmek için haritada başka bir yere tıklayın";
            } else if (mapTargetPickEnabled) {
                toggleMapTargetPickButton.textContent = "Haritadan Nokta Seç";
                toggleMapTargetPickButton.title = "Hedef konumunu seçmek için haritada bir noktaya tıkla";
            } else {
                toggleMapTargetPickButton.textContent = "Hedef Ekle";
                toggleMapTargetPickButton.title = "Haritada nokta seçip onaylayarak hedef tespiti oluştur";
            }
        }

        if (confirmMapTargetButton) {
            confirmMapTargetButton.hidden = !draftMapTarget;
            confirmMapTargetButton.disabled = mapTargetPickLoading || !draftMapTarget;
        }
        if (cancelMapTargetButton) {
            cancelMapTargetButton.hidden = !mapTargetPickEnabled && !draftMapTarget;
            cancelMapTargetButton.disabled = mapTargetPickLoading;
        }
        return;

        if (mapTargetPickLoading) {
            toggleMapTargetPickButton.textContent = "Hedef Ekleniyor";
            toggleMapTargetPickButton.title = "Tıklanan harita noktasında demo hedefi oluşturuluyor";
            return;
        }
        if (mapTargetPickEnabled) {
            toggleMapTargetPickButton.textContent = "Haritadan Nokta Seç";
            toggleMapTargetPickButton.title = "Hedef oluşturmak için haritada bir noktaya tıkla";
            return;
        }
        toggleMapTargetPickButton.textContent = "Hedef Ekle";
        toggleMapTargetPickButton.title = "Haritada nokta seçerek hedef tespiti oluştur";
    }

    function setMapTargetPickEnabled(enabled) {
        mapTargetPickEnabled = Boolean(enabled);
        if (mapTargetPickEnabled && fieldLayerDrawingEnabled) {
            fieldLayerDrawingEnabled = false;
            if (mapController && typeof mapController.setFieldLayerDrawingEnabled === "function") {
                mapController.setFieldLayerDrawingEnabled(false);
            }
            updateFieldLayerDraftUi();
        }
        if (!mapTargetPickEnabled) {
            draftMapTarget = null;
            draftMapContactId = "";
        }
        if (mapController && typeof mapController.setTargetPickingEnabled === "function") {
            mapController.setTargetPickingEnabled(mapTargetPickEnabled && !mapTargetPickLoading);
        }
        updateMapTargetPickButton();
        refreshMap();
    }

    function fieldLayerLabel(value) {
        return FIELD_LAYER_LABELS[String(value || "")] || String(value || "-");
    }

    function normalizeFieldLayerColor(value) {
        const cleanValue = String(value || "").trim().toLowerCase();
        return /^#[0-9a-f]{6}$/.test(cleanValue) ? cleanValue : null;
    }

    function fieldLayerTypeValue() {
        return fieldLayerTypeInput && FIELD_LAYER_COLOR_OPTIONS[fieldLayerTypeInput.value]
            ? fieldLayerTypeInput.value
            : "custom";
    }

    function fieldLayerColorOptions(type) {
        return FIELD_LAYER_COLOR_OPTIONS[type] || FIELD_LAYER_COLOR_OPTIONS.custom;
    }

    function fieldLayerDefaultColor(type) {
        const options = fieldLayerColorOptions(type);
        return options[0] ? options[0].value : "#a855f7";
    }

    function fieldLayerDisplayColor(layer) {
        const layerType = layer && layer.layer_type ? String(layer.layer_type) : "custom";
        if (layerType === "custom") {
            return normalizeFieldLayerColor(layer.style && layer.style.color) || fieldLayerDefaultColor(layerType);
        }
        return fieldLayerDefaultColor(layerType);
    }

    function selectedFieldLayerColor() {
        const layerType = fieldLayerTypeValue();
        const currentColor = normalizeFieldLayerColor(fieldLayerColorInput && fieldLayerColorInput.value);
        if (layerType === "custom") {
            return currentColor || fieldLayerDefaultColor(layerType);
        }
        const options = fieldLayerColorOptions(layerType);
        const matchedOption = options.find((option) => normalizeFieldLayerColor(option.value) === currentColor);
        return matchedOption ? matchedOption.value : fieldLayerDefaultColor(layerType);
    }

    function renderFieldLayerColorControls(forceDefault) {
        if (!fieldLayerColorInput) {
            return;
        }
        const layerType = fieldLayerTypeValue();
        const isCustom = layerType === "custom";
        const options = fieldLayerColorOptions(layerType);
        const currentColor = forceDefault ? fieldLayerDefaultColor(layerType) : selectedFieldLayerColor();

        fieldLayerColorInput.value = currentColor;
        fieldLayerColorInput.disabled = !isCustom;
        fieldLayerColorInput.title = isCustom
            ? "Özel katmanda renk serbestçe seçilebilir."
            : `${fieldLayerLabel(layerType)} için sabit renk kullanılır.`;
        fieldLayerColorInput.setAttribute("aria-disabled", isCustom ? "false" : "true");

        if (fieldLayerColorPalette) {
            const showPalette = !isCustom && options.length > 1;
            fieldLayerColorPalette.hidden = !showPalette;
            fieldLayerColorPalette.innerHTML = !showPalette
                ? ""
                : options.map((option) => {
                    const optionColor = normalizeFieldLayerColor(option.value) || fieldLayerDefaultColor(layerType);
                    const isSelected = optionColor === normalizeFieldLayerColor(currentColor);
                    return `
                        <button
                            type="button"
                            class="field-layer-color-swatch${isSelected ? " is-selected" : ""}"
                            style="--field-layer-choice: ${optionColor}"
                            data-field-layer-color="${optionColor}"
                            aria-label="${fieldLayerLabel(layerType)} - ${option.label}"
                            aria-pressed="${isSelected ? "true" : "false"}"
                            title="${option.label}"
                        ></button>
                    `;
                }).join("");
        }

        if (fieldLayerColorNote) {
            fieldLayerColorNote.textContent = isCustom
                ? "Özel Katman seçili: renk serbestçe belirlenebilir."
                : `${fieldLayerLabel(layerType)} için sabit ${options[0] ? options[0].label.toLocaleLowerCase("tr-TR") : "renk"} kullanılır.`;
        }
    }

    function updateFieldLayerDraftUi() {
        if (fieldLayerDrawStartButton) {
            fieldLayerDrawStartButton.textContent = fieldLayerDrawingEnabled ? "Çizim Aktif" : "Çizimi Başlat";
            fieldLayerDrawStartButton.classList.toggle("is-active", fieldLayerDrawingEnabled);
            fieldLayerDrawStartButton.setAttribute("aria-pressed", fieldLayerDrawingEnabled ? "true" : "false");
        }
        if (fieldLayerSaveButton) {
            fieldLayerSaveButton.disabled = readonly || draftFieldLayerPoints.length !== 4;
        }
        if (fieldLayerCancelButton) {
            fieldLayerCancelButton.disabled = readonly || (!fieldLayerDrawingEnabled && !draftFieldLayerPoints.length);
        }
        if (fieldLayerDraftStatus) {
            if (fieldLayerDrawingEnabled && draftFieldLayerPoints.length === 4) {
                fieldLayerDraftStatus.textContent = "Alan hazır. Köşe ve kenar noktalarını sürükleyerek boyutu ayarlayabilirsiniz.";
            } else if (fieldLayerDrawingEnabled) {
                fieldLayerDraftStatus.textContent = "Haritada sol tıkla sürükleyerek dikdörtgen alan seçin; sağ tıkla sürükleyerek haritada dolaşın.";
            } else if (draftFieldLayerPoints.length) {
                fieldLayerDraftStatus.textContent = "Alan hazır. Kaydedebilir veya çizimi yeniden başlatabilirsiniz.";
            } else {
                fieldLayerDraftStatus.textContent = "Çizim başlatılmadı.";
            }
        }
        renderProgressPanel();
        renderTaskTimeline();
    }

    function setFieldLayerDrawingEnabled(enabled) {
        fieldLayerDrawingEnabled = Boolean(enabled) && !readonly;
        if (fieldLayerDrawingEnabled) {
            setMapTargetPickEnabled(false);
        }
        if (mapController && typeof mapController.setFieldLayerDrawingEnabled === "function") {
            mapController.setFieldLayerDrawingEnabled(fieldLayerDrawingEnabled);
        }
        updateFieldLayerDraftUi();
        refreshMap();
    }

    function clearFieldLayerDraft() {
        draftFieldLayerPoints = [];
        setFieldLayerDrawingEnabled(false);
        updateFieldLayerDraftUi();
        refreshMap();
    }

    function normalizeDraftFieldLayerPoints(points) {
        if (!Array.isArray(points)) {
            return [];
        }
        const cleanPoints = points
            .map((point) => Array.isArray(point) && point.length >= 2 ? [Number(point[0]), Number(point[1])] : null)
            .filter((point) => point && Number.isFinite(point[0]) && Number.isFinite(point[1]));
        return cleanPoints.length === 4 ? cleanPoints : [];
    }

    function handleFieldLayerDraftChange(change) {
        if (readonly) {
            return;
        }
        draftFieldLayerPoints = normalizeDraftFieldLayerPoints(change && change.points);
        updateFieldLayerDraftUi();
        refreshMap();
    }

    function draftFieldLayerGeometry() {
        if (draftFieldLayerPoints.length !== 4) {
            return null;
        }
        const ring = draftFieldLayerPoints.map((point) => [point[1], point[0]]);
        ring.push([draftFieldLayerPoints[0][1], draftFieldLayerPoints[0][0]]);
        return {
            type: "Polygon",
            coordinates: [ring]
        };
    }

    async function saveFieldLayer(event) {
        event.preventDefault();
        if (readonly) {
            return;
        }
        const geometry = draftFieldLayerGeometry();
        if (!geometry) {
            showFlash("Saha katmanı için haritada sol tıkla sürükleyerek bir alan seçin.", true);
            return;
        }
        const name = fieldLayerNameInput ? fieldLayerNameInput.value.trim() : "";
        if (!name) {
            showFlash("Saha katmanı adı zorunlu.", true);
            return;
        }
        const payload = {
            name,
            layer_type: fieldLayerTypeValue(),
            geometry,
            style: {
                color: selectedFieldLayerColor(),
                fillOpacity: 0.14
            },
            is_active: true
        };
        try {
            await fetchJson("/v1/field-layers", {
                method: "POST",
                body: JSON.stringify(payload)
            });
            if (fieldLayerForm) {
                fieldLayerForm.reset();
            }
            renderFieldLayerColorControls(true);
            clearFieldLayerDraft();
            showFlash(`${name} saha katmanı kaydedildi.`, false);
            await refreshAll();
        } catch (error) {
            showFlash(`Saha katmanı kaydedilemedi: ${error.message}`, true);
        }
    }

    function stopReplayTimer() {
        if (replayState.timer) {
            window.clearInterval(replayState.timer);
            replayState.timer = null;
        }
        replayState.playing = false;
    }

    function replaySpeed() {
        const value = replaySpeedSelect ? Number(replaySpeedSelect.value) : 2;
        return Number.isFinite(value) && value > 0 ? value : 2;
    }

    function replayEventMarkers(task) {
        if (!task) {
            return [];
        }
        const base = { lat: task.target_lat, lon: task.target_lon };
        return [
            { ...base, timestamp: task.assigned_at, label: "Görev atandı" },
            task.accepted_at ? { ...base, timestamp: task.accepted_at, label: "Görev kabul edildi" } : null,
            task.rejected_at ? { ...base, timestamp: task.rejected_at, label: "Görev reddedildi" } : null,
            task.completed_at ? { ...base, timestamp: task.completed_at, label: "Görev tamamlandı" } : null
        ].filter(Boolean);
    }

    function collectReplayTimes(tracks, events) {
        return tracks
            .flatMap((track) => Array.isArray(track.points) ? track.points : [])
            .map((point) => new Date(point.timestamp).getTime())
            .concat(events.map((event) => new Date(event.timestamp).getTime()))
            .filter((value) => Number.isFinite(value))
            .sort((left, right) => left - right);
    }

    function updateReplayControls() {
        const hasReplay = replayState.minTime !== null && replayState.maxTime !== null && replayState.maxTime >= replayState.minTime;
        if (replayPlayButton) {
            replayPlayButton.disabled = !hasReplay;
            replayPlayButton.textContent = replayState.playing ? "Duraklat" : "Oynat";
        }
        if (replaySlider) {
            replaySlider.disabled = !hasReplay;
            if (hasReplay) {
                const span = Math.max(1, replayState.maxTime - replayState.minTime);
                replaySlider.value = String(Math.round(((replayState.cursorTime - replayState.minTime) / span) * 1000));
            } else {
                replaySlider.value = "1000";
            }
        }
        if (replaySpeedSelect) {
            replaySpeedSelect.disabled = !hasReplay;
        }
        const task = latestState.tasks.find((item) => item.id === replayState.taskId) || null;
        if (replayTitle) {
            replayTitle.textContent = task ? `${task.contact_id} / ${task.interceptor_drone_uid}` : "Görev seçilmedi";
        }
        if (replayClock) {
            replayClock.textContent = hasReplay ? new Date(replayState.cursorTime).toLocaleTimeString("tr-TR") : "--:--:--";
        }
        if (replayStatus) {
            if (!task) {
                replayStatus.textContent = "Replay için aktif görev seçin.";
            } else if (!hasReplay) {
                replayStatus.textContent = "Bu görev için playback noktası henüz yok.";
            } else {
                const pointCount = replayState.tracks.reduce((total, track) => total + (track.points ? track.points.length : 0), 0);
                replayStatus.textContent = `${pointCount} iz noktası ve ${replayState.events.length} görev olayı yüklendi.`;
            }
        }
    }

    function clearReplay() {
        stopReplayTimer();
        replayState = {
            taskId: null,
            tracks: [],
            events: [],
            minTime: null,
            maxTime: null,
            cursorTime: null,
            playing: false,
            timer: null
        };
        updateReplayControls();
        refreshMap();
    }

    function setReplayCursorFromSlider() {
        if (replayState.minTime === null || replayState.maxTime === null || !replaySlider) {
            return;
        }
        const percent = Number(replaySlider.value) / 1000;
        replayState.cursorTime = replayState.minTime + (replayState.maxTime - replayState.minTime) * percent;
        updateReplayControls();
        refreshMap();
    }

    function toggleReplayPlayback() {
        if (replayState.minTime === null || replayState.maxTime === null) {
            return;
        }
        if (replayState.playing) {
            stopReplayTimer();
            updateReplayControls();
            return;
        }
        replayState.playing = true;
        replayState.timer = window.setInterval(() => {
            replayState.cursorTime = Math.min(replayState.maxTime, replayState.cursorTime + (1000 * replaySpeed()));
            if (replayState.cursorTime >= replayState.maxTime) {
                stopReplayTimer();
            }
            updateReplayControls();
            refreshMap();
        }, 500);
        updateReplayControls();
    }

    async function loadReplayForTask(task) {
        if (!task) {
            clearReplay();
            return;
        }
        if (replayState.taskId === task.id && replayState.tracks.length) {
            replayState.events = replayEventMarkers(task);
            updateReplayControls();
            refreshMap();
            return;
        }
        stopReplayTimer();
        replayState.taskId = task.id;
        replayState.tracks = [];
        replayState.events = replayEventMarkers(task);
        replayState.minTime = null;
        replayState.maxTime = null;
        replayState.cursorTime = null;
        updateReplayControls();
        try {
            const [recon, interceptor] = await Promise.all([
                fetchJson(`/v1/tracks/${encodeURIComponent(task.recon_drone_uid)}/playback?minutes=60`),
                fetchJson(`/v1/tracks/${encodeURIComponent(task.interceptor_drone_uid)}/playback?minutes=60`)
            ]);
            if (replayState.taskId !== task.id) {
                return;
            }
            const tracks = [
                { drone_uid: task.recon_drone_uid, platform_role: "recon", points: recon.points || [] },
                { drone_uid: task.interceptor_drone_uid, platform_role: "interceptor", points: interceptor.points || [] }
            ];
            const times = collectReplayTimes(tracks, replayState.events);
            replayState.tracks = tracks;
            replayState.minTime = times.length ? times[0] : null;
            replayState.maxTime = times.length ? times[times.length - 1] : null;
            replayState.cursorTime = replayState.maxTime;
            updateReplayControls();
            refreshMap();
        } catch (error) {
            if (replayStatus) {
                replayStatus.textContent = `Replay yüklenemedi: ${error.message}`;
            }
        }
    }

    function syncReplayTask() {
        const task = latestState.tasks.find((item) => item.id === selectedTaskId) || null;
        if (!task) {
            if (replayState.taskId) {
                clearReplay();
            } else {
                updateReplayControls();
            }
            return;
        }
        loadReplayForTask(task);
    }

    function formatEta(seconds) {
        if (!Number.isFinite(seconds) || seconds < 0) {
            return "hız bekleniyor";
        }
        if (seconds < 60) {
            return `${Math.ceil(seconds)} sn`;
        }
        return `${Math.floor(seconds / 60)} dk ${Math.ceil(seconds % 60)} sn`;
    }

    function renderProgressPanel() {
        if (!progressPanel) {
            return;
        }
        const task = latestState.tasks.find((item) => item.id === selectedTaskId) || null;
        if (!task || !window.HavaMap) {
            progressPanel.className = "progress-panel empty-state";
            progressPanel.textContent = "Aktif görev seçildiğinde kalan mesafe, ETA ve ilerleme burada gösterilir.";
            return;
        }
        const station = latestState.stations.find((item) => item.id === task.operator_station_id) || null;
        const interceptorTrack = latestState.tracks.find((item) => item.drone_uid === task.interceptor_drone_uid) || null;
        const total = station
            ? window.HavaMap.distanceMeters(station.lat, station.lon, task.target_lat, task.target_lon)
            : Number(task.range_m || 0);
        const remaining = interceptorTrack
            ? window.HavaMap.distanceMeters(interceptorTrack.lat, interceptorTrack.lon, task.target_lat, task.target_lon)
            : null;
        const progress = remaining === null || total <= 0
            ? 0
            : Math.max(0, Math.min(100, ((total - remaining) / total) * 100));
        const speed = interceptorTrack ? Number(interceptorTrack.speed_mps || 0) : 0;
        const eta = remaining !== null && speed > 0.5 ? formatEta(remaining / speed) : "hız bekleniyor";
        progressPanel.className = "progress-panel";
        progressPanel.innerHTML = `
            <div class="progress-readout">
                <strong>${Math.round(progress)}%</strong>
                <span>${task.contact_id} / ${task.interceptor_drone_uid}</span>
            </div>
            <div class="progress-bar"><span style="width: ${progress}%"></span></div>
            <div class="progress-grid">
                <span><b>Toplam</b>${Math.round(total)} m</span>
                <span><b>Kalan</b>${remaining === null ? "-" : `${Math.round(remaining)} m`}</span>
                <span><b>ETA</b>${eta}</span>
                <span><b>Hız</b>${speed > 0 ? `${speed.toFixed(1)} m/s` : "-"}</span>
            </div>
        `;
    }

    function renderTaskTimeline() {
        if (!taskTimeline) {
            return;
        }
        const task = latestState.tasks.find((item) => item.id === selectedTaskId) || null;
        if (!task) {
            taskTimeline.className = "task-timeline empty-state";
            taskTimeline.textContent = "Görev seçildiğinde operasyon adımları burada gösterilir.";
            return;
        }
        const detection = latestState.detections.find((item) => item.id === task.hostile_detection_id) || null;
        const terminalLabel = task.status === "completed"
            ? "Tamamlandı"
            : task.status === "rejected"
                ? "Reddedildi"
                : task.status === "expired"
                    ? "Süre Doldu"
                    : "Kapanış bekliyor";
        const steps = [
            { label: "Hedef Tespiti", time: detection ? detection.created_at : task.assigned_at, done: true },
            { label: "İstasyon Atandı", time: task.assigned_at, done: true },
            { label: "Görev Bekliyor", time: task.assigned_at, done: true },
            { label: "Kabul", time: task.accepted_at, done: Boolean(task.accepted_at) },
            { label: terminalLabel, time: task.completed_at || task.rejected_at || null, done: ["completed", "rejected", "expired"].includes(task.status) }
        ];
        taskTimeline.className = "task-timeline";
        taskTimeline.innerHTML = steps.map((step, index) => `
            <div class="timeline-step ${step.done ? "done" : "pending"}">
                <span>${index + 1}</span>
                <strong>${step.label}</strong>
                <small>${step.time ? formatTime(step.time) : "Bekliyor"}</small>
            </div>
        `).join("");
    }

    function hasDemoScenario() {
        return latestState.tracks.some((item) => item.drone_uid === "DEMO-RECON-01")
            && latestState.stations.some((item) => String(item.assigned_interceptor_drone_uid || "").startsWith("DEMO-INT-"));
    }

    function nextMapContactId() {
        mapTargetSequence += 1;
        const stamp = Date.now().toString(36).toUpperCase();
        return `HST-DEMO-MAP-${stamp}-${String(mapTargetSequence).padStart(3, "0")}`;
    }

    function isClosedTarget(item) {
        return ["resolved", "cancelled"].includes(String(item && item.status ? item.status : "").toLowerCase());
    }

    function syncMapCreatedTargets(detections) {
        const backendByContact = new Map(detections.map((item) => [item.contact_id, item]));
        mapCreatedTargets = mapCreatedTargets
            .map((item) => backendByContact.get(item.contact_id) || item)
            .filter((item) => !isClosedTarget(item));
    }

    function mapDetectionsForDisplay() {
        const backendContacts = new Set(latestState.detections.map((item) => item.contact_id));
        return latestState.detections.concat(
            mapCreatedTargets.filter((item) => !backendContacts.has(item.contact_id) && !isClosedTarget(item))
        );
    }

    function setTargetFormCoordinates(lat, lon) {
        const latField = document.getElementById("demo-target-lat");
        const lonField = document.getElementById("demo-target-lon");
        if (latField) {
            latField.value = Number(lat).toFixed(6);
        }
        if (lonField) {
            lonField.value = Number(lon).toFixed(6);
        }
    }

    function numberFieldValue(elementId, fallback) {
        const field = document.getElementById(elementId);
        if (!field) {
            return fallback;
        }
        const value = Number(field.value);
        return Number.isFinite(value) ? value : fallback;
    }

    function readDemoDetectionPayload(contactId) {
        return {
            contact_id: contactId || document.getElementById("demo-contact-id").value.trim(),
            target_lat: numberFieldValue("demo-target-lat", 40.8445),
            target_lon: numberFieldValue("demo-target-lon", 29.3335),
            target_alt_m: numberFieldValue("demo-target-alt", 350),
            confidence: numberFieldValue("demo-confidence", 88)
        };
    }

    function readMapTargetPayload() {
        if (!draftMapTarget) {
            return null;
        }
        const targetLat = Number(draftMapTarget.lat);
        const targetLon = Number(draftMapTarget.lon);
        if (!Number.isFinite(targetLat) || !Number.isFinite(targetLon)) {
            return null;
        }
        return {
            contact_id: draftMapContactId || nextMapContactId(),
            target_lat: targetLat,
            target_lon: targetLon,
            target_alt_m: numberFieldValue("demo-target-alt", 350),
            confidence: numberFieldValue("demo-confidence", 88)
        };
    }

    function renderDemoDetectionResult(result) {
        if (demoLastDetectionNode) {
            demoLastDetectionNode.className = "detail-grid";
            demoLastDetectionNode.innerHTML = `
                <div class="detail-item"><strong>Temas</strong><span>${result.detection.contact_id}</span></div>
                <div class="detail-item"><strong>Atanan İstasyon</strong><span>${result.assigned_station_name || "-"}</span></div>
                <div class="detail-item"><strong>Operatör</strong><span>${result.assigned_operator_username || "-"}</span></div>
                <div class="detail-item"><strong>Görev</strong><span>${result.assigned_task_id || "-"}</span></div>
            `;
        }
        selectedDetectionId = result.detection.id;
        selectedTaskId = result.assigned_task_id || null;
        selectedFieldLayerId = null;
        setDemoStepState("detection", "done");
        setDemoStepState("operator", "active");
    }

    async function createDemoDetection(payload, pendingMessage) {
        setDemoStepState("detection", "active");
        setDemoDetectionMessage(pendingMessage, false);
        const result = await fetchJson("/v1/demo/detections", {
            method: "POST",
            body: JSON.stringify(payload)
        });
        renderDemoDetectionResult(result);
        return result;
    }

    async function handleMapTargetClick(point) {
        if (!mapTargetPickEnabled || mapTargetPickLoading || readonly) {
            return;
        }
        clearFlash();
        if (!hasDemoScenario()) {
            showFlash("Haritadan hedef oluşturmak için önce Sunum Akışı bölümünden demo senaryoyu kurun.", true);
            return;
        }

        draftMapContactId = nextMapContactId();
        const draftContactField = document.getElementById("demo-contact-id");
        if (draftContactField) {
            draftContactField.value = draftMapContactId;
        }
        setTargetFormCoordinates(point.lat, point.lon);
        draftMapTarget = { lat: point.lat, lon: point.lon };
        updateMapTargetPickButton();
        refreshMap();
        showFlash(`Hedef noktası seçildi: ${formatCoord(point.lat, point.lon)}. Kaydetmek için Hedefi Onayla düğmesine basın.`, false);
        return;

        const contactId = nextMapContactId();
        const contactField = document.getElementById("demo-contact-id");
        if (contactField) {
            contactField.value = contactId;
        }
        setTargetFormCoordinates(point.lat, point.lon);
        draftMapTarget = { lat: point.lat, lon: point.lon };
        const payload = readMapTargetPayload();
        if (!payload) {
            showFlash("Önce haritada hedef noktası seçin.", true);
            return;
        }

        mapTargetPickLoading = true;
        if (mapController && typeof mapController.setTargetPickingEnabled === "function") {
            mapController.setTargetPickingEnabled(false);
        }
        updateMapTargetPickButton();
        refreshMap();

        try {
            const result = await createDemoDetection(
                readDemoDetectionPayload(contactId),
                `Harita noktasında hedef oluşturuluyor: ${formatCoord(point.lat, point.lon)}`
            );
            mapCreatedTargets = [result.detection]
                .concat(mapCreatedTargets.filter((item) => item.contact_id !== result.detection.contact_id))
                .filter((item) => !isClosedTarget(item));
            draftMapTarget = null;
            mapTargetPickEnabled = false;
            showFlash(`Haritadan hedef oluşturuldu ve en yakın operatöre atandı: ${result.assigned_station_name || "-"}`, false);
            refreshMap();
            await refreshAll();
        } catch (error) {
            setDemoStepState("detection", "idle");
            setDemoDetectionMessage(`Haritadan hedef oluşturulamadı: ${error.message}`, true);
            showFlash(`Haritadan hedef oluşturulamadı: ${error.message}`, true);
        } finally {
            mapTargetPickLoading = false;
            if (mapController && typeof mapController.setTargetPickingEnabled === "function") {
                mapController.setTargetPickingEnabled(mapTargetPickEnabled);
            }
            updateMapTargetPickButton();
            refreshMap();
        }
    }

    async function confirmMapTargetSelection() {
        if (!draftMapTarget || mapTargetPickLoading || readonly) {
            return;
        }
        clearFlash();
        const payload = readMapTargetPayload();
        if (!payload) {
            showFlash("Önce haritada hedef noktası seçin.", true);
            return;
        }
        if (!hasDemoScenario()) {
            showFlash("Haritadan hedef oluşturmak için önce Sunum Akışı bölümünden demo senaryoyu kurun.", true);
            return;
        }

        mapTargetPickLoading = true;
        if (mapController && typeof mapController.setTargetPickingEnabled === "function") {
            mapController.setTargetPickingEnabled(false);
        }
        updateMapTargetPickButton();
        refreshMap();

        try {
            const result = await createDemoDetection(
                payload,
                `Seçilen harita noktasında hedef oluşturuluyor: ${formatCoord(draftMapTarget.lat, draftMapTarget.lon)}`
            );
            mapCreatedTargets = [result.detection]
                .concat(mapCreatedTargets.filter((item) => item.contact_id !== result.detection.contact_id))
                .filter((item) => !isClosedTarget(item));
            draftMapTarget = null;
            draftMapContactId = "";
            mapTargetPickEnabled = false;
            showFlash(`Hedef kaydedildi ve en yakın operatöre atandı: ${result.assigned_station_name || "-"}`, false);
            refreshMap();
            await refreshAll();
        } catch (error) {
            setDemoStepState("detection", "idle");
            setDemoDetectionMessage(`Haritadan hedef oluşturulamadı: ${error.message}`, true);
            showFlash(`Haritadan hedef oluşturulamadı: ${error.message}`, true);
        } finally {
            mapTargetPickLoading = false;
            if (mapController && typeof mapController.setTargetPickingEnabled === "function") {
                mapController.setTargetPickingEnabled(mapTargetPickEnabled);
            }
            updateMapTargetPickButton();
            refreshMap();
        }
    }

    function cancelMapTargetSelection(message) {
        draftMapTarget = null;
        draftMapContactId = "";
        setMapTargetPickEnabled(false);
        if (message) {
            showFlash(message, false);
        }
    }

    function formatCoord(lat, lon) {
        return `${Number(lat).toFixed(5)}, ${Number(lon).toFixed(5)}`;
    }

    function formatTime(value) {
        if (!value) {
            return "-";
        }
        return new Date(value).toLocaleString("tr-TR");
    }

    function roleLabel(value) {
        return ROLE_LABELS[String(value || "").toLowerCase()] || String(value || "-");
    }

    function statusLabel(value) {
        const clean = String(value || "").toLowerCase();
        return STATUS_LABELS[clean] || String(value || "-");
    }

    function statusChip(status) {
        const clean = String(status || "").toLowerCase();
        let tone = "warning";
        if (["resolved", "completed", "accepted", "assigned", "active"].includes(clean)) {
            tone = "planli";
        } else if (["rejected", "cancelled", "expired", "inactive"].includes(clean)) {
            tone = "bad";
        }
        return `<span class="status-chip ${tone}">${statusLabel(status)}</span>`;
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

    function fieldLayerEffectCardClass(item) {
        const effect = topFieldLayerEffect(item);
        if (!effect) {
            return "";
        }
        const severity = String(effect.severity || "info").toLowerCase();
        return `has-field-effect effect-${severity}`;
    }

    function compareByFieldLayerEffect(left, right) {
        const effectDelta = fieldLayerEffectRank(topFieldLayerEffect(right)) - fieldLayerEffectRank(topFieldLayerEffect(left));
        if (effectDelta !== 0) {
            return effectDelta;
        }
        return String(right.updated_at || right.assigned_at || "").localeCompare(String(left.updated_at || left.assigned_at || ""));
    }

    function renderFieldLayerEffectBadges(item) {
        const effects = fieldLayerEffects(item);
        if (!effects.length) {
            return "";
        }
        return `
            <div class="field-effect-strip" aria-label="Saha katmanı etkileri">
                ${effects.map((effect) => {
                    const severity = String(effect.severity || "info").toLowerCase();
                    const severityLabel = FIELD_LAYER_EFFECT_LABELS[severity] || severity;
                    return `<span class="field-effect-badge effect-${severity}" title="${effect.layer_name}">${severityLabel}: ${effect.label}</span>`;
                }).join("")}
            </div>
        `;
    }

    function fieldLayerEffectFocusText(item) {
        const effect = topFieldLayerEffect(item);
        return effect ? `${effect.label}: ${effect.layer_name}` : "";
    }

    function isDemoDetection(item) {
        return String(item.contact_id || "").startsWith("HST-DEMO")
            || String(item.recon_drone_uid || "") === "DEMO-RECON-01";
    }

    function isDemoTask(item) {
        return String(item.contact_id || "").startsWith("HST-DEMO")
            || String(item.recon_drone_uid || "") === "DEMO-RECON-01";
    }

    function setDemoStepState(step, state) {
        const node = document.querySelector(`[data-demo-step="${step}"]`);
        if (!node) {
            return;
        }
        node.dataset.state = state;
    }

    function setDemoResetResult(message, isError) {
        if (!demoResetResultNode) {
            return;
        }
        demoResetResultNode.className = isError ? "error-box" : "success-box";
        demoResetResultNode.textContent = message;
    }

    function updateDemoFlowState() {
        if (!document.getElementById("demo-flow-strip")) {
            return;
        }
        const hasScenario = latestState.tracks.some((item) => item.drone_uid === "DEMO-RECON-01")
            && latestState.stations.some((item) => String(item.assigned_interceptor_drone_uid || "").startsWith("DEMO-INT-"));
        const demoDetection = latestState.detections.find(isDemoDetection) || null;
        const demoTask = latestState.tasks.find(isDemoTask) || null;

        setDemoStepState("reset", hasScenario || demoDetection || demoTask ? "idle" : "done");
        setDemoStepState("scenario", hasScenario ? "done" : "active");
        setDemoStepState("detection", demoDetection ? "done" : hasScenario ? "active" : "idle");
        setDemoStepState("operator", demoTask ? "done" : demoDetection ? "active" : "idle");
        setDemoStepState("intercept", demoTask && demoTask.status === "completed" ? "done" : demoTask ? "active" : "idle");
    }

    function ensureSelection() {
        if (selectedTaskId && !latestState.tasks.some((task) => task.id === selectedTaskId)) {
            selectedTaskId = null;
        }
        const detectionPool = latestState.detections.concat(mapCreatedTargets);
        if (selectedDetectionId && !detectionPool.some((item) => item.id === selectedDetectionId)) {
            selectedDetectionId = null;
        }
        if (selectedFieldLayerId && !latestState.fieldLayers.some((layer) => layer.id === selectedFieldLayerId)) {
            selectedFieldLayerId = null;
        }
        if (!selectedTaskId && !selectedDetectionId && !selectedFieldLayerId && latestState.tasks.length) {
            const priorityTask = latestState.tasks.find((task) => task.status === "accepted")
                || latestState.tasks.find((task) => task.status === "pending")
                || latestState.tasks[0];
            selectedTaskId = priorityTask.id;
        }
    }

    function refreshMap() {
        ensureSelection();
        const mapDetections = mapDetectionsForDisplay();
        if (mapController) {
            mapController.setState({
                tracks: latestState.tracks,
                detections: mapDetections,
                stations: latestState.stations,
                tasks: latestState.tasks,
                fieldLayers: latestState.fieldLayers,
                aircraft: airTrafficEnabled ? latestState.aircraft : [],
                draftTarget: draftMapTarget,
                draftFieldLayer: {
                    points: draftFieldLayerPoints,
                    layer_type: fieldLayerTypeValue(),
                    style: {
                        color: selectedFieldLayerColor(),
                        fillOpacity: 0.14
                    }
                },
                playbackTracks: replayState.tracks,
                replayCursor: replayState.cursorTime ? new Date(replayState.cursorTime).toISOString() : null,
                replayEvents: replayState.events,
                focus: {
                    taskId: selectedTaskId,
                    detectionId: selectedDetectionId,
                    fieldLayerId: selectedFieldLayerId
                }
            });
        }

        const focusedTask = latestState.tasks.find((item) => item.id === selectedTaskId) || null;
        const focusedDetection = mapDetections.find((item) => item.id === selectedDetectionId)
            || (focusedTask ? mapDetections.find((item) => item.id === focusedTask.hostile_detection_id) || null : null);
        const focusedFieldLayer = latestState.fieldLayers.find((item) => item.id === selectedFieldLayerId) || null;

        if (mapSummaryNode) {
            const activeTasks = latestState.tasks.filter((item) => ["pending", "accepted"].includes(item.status)).length;
            const criticalEffects = latestState.detections.filter((item) => {
                const effect = topFieldLayerEffect(item);
                return effect && String(effect.severity || "").toLowerCase() === "critical";
            }).length;
            const airTrafficText = airTrafficEnabled
                ? ` ${latestState.aircraft.length} sivil hava aracı ayrı katmanda gösteriliyor.`
                : "";
            const fieldLayerText = latestState.fieldLayers.length
                ? ` ${latestState.fieldLayers.length} saha katmanı aktif.`
                : "";
            const effectText = criticalEffects ? ` ${criticalEffects} kritik katman teması var.` : "";
            mapSummaryNode.textContent = `${latestState.tracks.length} canlı iz, ${latestState.detections.length} düşman hedefi ve ${activeTasks} aktif angajman sahada izleniyor.${fieldLayerText}${effectText}${airTrafficText}`;
        }

        if (mapFocusNode) {
            if (fieldLayerDrawingEnabled) {
                mapFocusNode.textContent = "Saha katmanı çizimi aktif. Sol tıkla alan seçin, sağ tıkla haritada dolaşın; tutamaçlarla boyutu ayarlayın.";
                return;
            }
            if (draftFieldLayerPoints.length) {
                mapFocusNode.textContent = "Saha katmanı alanı hazır. Kaydetmeden önce köşe veya kenar tutamaçlarını sürükleyebilirsiniz.";
                return;
            }
            if (draftMapTarget && !mapTargetPickLoading) {
                mapFocusNode.textContent = "Hedef noktası seçildi. Kaydı oluşturmak ve en yakın operatöre atamak için Hedefi Onayla düğmesine basın.";
                return;
            }
            if (mapTargetPickLoading) {
                mapFocusNode.textContent = "Tıklanan noktada hedef kaydı oluşturuluyor ve en yakın operatör hesaplanıyor.";
            } else if (mapTargetPickEnabled) {
                mapFocusNode.textContent = "Hedef oluşturmak için haritada bir noktaya tıklayın. Koordinat otomatik alınacak.";
            } else if (focusedTask) {
                const interceptorTrack = latestState.tracks.find((item) => item.drone_uid === focusedTask.interceptor_drone_uid);
                const effectText = fieldLayerEffectFocusText(focusedTask);
                const remaining = interceptorTrack && window.HavaMap
                    ? window.HavaMap.distanceMeters(
                        interceptorTrack.lat,
                        interceptorTrack.lon,
                        focusedTask.target_lat,
                        focusedTask.target_lon
                    )
                    : null;
                mapFocusNode.textContent = remaining === null
                    ? `Odak görev: ${focusedTask.contact_id} / ${focusedTask.interceptor_drone_uid} -> ${focusedTask.operator_station_name}${effectText ? ` / ${effectText}` : ""}`
                    : `Odak görev: ${focusedTask.contact_id}. ${focusedTask.interceptor_drone_uid} hedefe yaklaşık ${Math.round(remaining)} m mesafede.${effectText ? ` ${effectText}` : ""}`;
            } else if (focusedDetection) {
                const effectText = fieldLayerEffectFocusText(focusedDetection);
                mapFocusNode.textContent = `Odak hedef: ${focusedDetection.contact_id} / ${formatCoord(focusedDetection.target_lat, focusedDetection.target_lon)}${effectText ? ` / ${effectText}` : ""}`;
            } else if (focusedFieldLayer) {
                mapFocusNode.textContent = `Odak saha katmanı: ${focusedFieldLayer.name} / ${fieldLayerLabel(focusedFieldLayer.layer_type)}. Harita katman sınırına taşındı.`;
            } else {
                mapFocusNode.textContent = airTrafficEnabled && airTrafficLastError
                    ? `Sivil trafik verisi alınamadı: ${airTrafficLastError}`
                    : "Bir hedef veya görev seçerek odağı daraltabilirsiniz.";
            }
        }
    }

    function renderTracks(tracks) {
        document.getElementById("metric-track-total").textContent = String(tracks.length);
        const reconCount = tracks.filter((item) => item.platform_role === "recon").length;
        const interceptorCount = tracks.filter((item) => item.platform_role === "interceptor").length;
        document.getElementById("metric-track-breakdown").textContent = `Keşif ${reconCount} / Önleyici ${interceptorCount}`;

        if (!tracks.length) {
            tracksBody.innerHTML = '<tr><td colspan="6">Henüz iz yok.</td></tr>';
            return;
        }

        tracksBody.innerHTML = tracks.map((track) => `
            <tr>
                <td>${track.drone_uid}</td>
                <td>${roleLabel(track.platform_role)}</td>
                <td>${formatCoord(track.lat, track.lon)}</td>
                <td>${Number(track.speed_mps).toFixed(1)} m/s</td>
                <td>${Number(track.heading_deg).toFixed(1)}°</td>
                <td>${formatTime(track.last_seen_at)}</td>
            </tr>
        `).join("");
    }

    function renderDetections(detections) {
        document.getElementById("metric-detection-total").textContent = String(detections.length);
        const openCount = detections.filter((item) => item.status === "open").length;
        const assignedCount = detections.filter((item) => item.status === "assigned").length;
        const resolvedCount = detections.filter((item) => item.status === "resolved").length;
        document.getElementById("metric-detection-breakdown").textContent = `Açık ${openCount} / Atanmış ${assignedCount} / İmha ${resolvedCount}`;

        if (!detections.length) {
            detectionsList.innerHTML = '<div class="empty-state">Hedef tespiti yok.</div>';
            return;
        }

        const orderedDetections = detections.slice().sort(compareByFieldLayerEffect);
        detectionsList.innerHTML = orderedDetections.map((item) => `
            <article class="task-card ${selectedDetectionId === item.id ? "selected" : ""} ${fieldLayerEffectCardClass(item)}" data-detection-id="${item.id}" tabindex="0">
                <div class="info-card-head">
                    <div>
                        <strong>${item.contact_id}</strong>
                        <small>${item.recon_drone_uid}</small>
                    </div>
                    <div class="card-actions">
                        ${statusChip(item.status)}
                        ${readonly ? "" : `<button type="button" class="danger-btn target-delete-btn" data-detection-delete-id="${item.id}">Hedefi Sil</button>`}
                    </div>
                </div>
                ${renderFieldLayerEffectBadges(item)}
                <div class="info-grid">
                    <span>Hedef: ${formatCoord(item.target_lat, item.target_lon)}</span>
                    <span>Alt: ${Number(item.target_alt_m).toFixed(1)} m</span>
                    <span>Yönelim: ${Number(item.bearing_mil).toFixed(1)} mil / ${Number(item.true_bearing_deg).toFixed(1)}°</span>
                    <span>Menzil: ${Number(item.range_m).toFixed(1)} m</span>
                    <span>İstasyon: ${item.assigned_operator_station_name || "-"}</span>
                </div>
            </article>
        `).join("");

        detectionsList.querySelectorAll("[data-detection-id]").forEach((button) => {
            button.addEventListener("click", () => {
                selectedDetectionId = button.getAttribute("data-detection-id");
                selectedFieldLayerId = null;
                const linkedTask = latestState.tasks.find((task) => task.hostile_detection_id === selectedDetectionId);
                selectedTaskId = linkedTask ? linkedTask.id : null;
                renderDetections(latestState.detections);
                renderTasks(latestState.tasks);
                refreshMap();
                syncReplayTask();
            });
            button.addEventListener("keydown", (event) => {
                if (event.key !== "Enter" && event.key !== " ") {
                    return;
                }
                event.preventDefault();
                button.click();
            });
        });

        detectionsList.querySelectorAll("[data-detection-delete-id]").forEach((button) => {
            button.addEventListener("click", async (event) => {
                event.stopPropagation();
                const detectionId = button.getAttribute("data-detection-delete-id");
                const detection = latestState.detections.find((item) => item.id === detectionId);
                if (!detectionId || !detection) {
                    return;
                }
                if (!window.confirm(`${detection.contact_id} hedef tespiti ve bağlı görevler silinsin mi?`)) {
                    return;
                }
                try {
                    button.disabled = true;
                    await fetchJson(`/v1/hostile-detections/${encodeURIComponent(detectionId)}`, { method: "DELETE" });
                    if (selectedDetectionId === detectionId) {
                        selectedDetectionId = null;
                    }
                    const linkedTaskIds = latestState.tasks
                        .filter((task) => task.hostile_detection_id === detectionId)
                        .map((task) => task.id);
                    if (linkedTaskIds.includes(selectedTaskId)) {
                        selectedTaskId = null;
                    }
                    mapCreatedTargets = mapCreatedTargets.filter((item) => item.id !== detectionId);
                    showFlash(`${detection.contact_id} hedef tespiti silindi.`, false);
                    await refreshAll();
                } catch (error) {
                    button.disabled = false;
                    showFlash(`Hedef tespiti silinemedi: ${error.message}`, true);
                }
            });
        });
    }

    function renderStations(stations) {
        document.getElementById("metric-station-total").textContent = String(stations.length);
        const activeCount = stations.filter((item) => item.is_active).length;
        document.getElementById("metric-station-breakdown").textContent = `Aktif ${activeCount}`;

        if (!stations.length) {
            stationsList.innerHTML = '<div class="empty-state">Operatör istasyonu yok.</div>';
            return;
        }

        stationsList.innerHTML = stations.map((item) => `
            <article class="info-card">
                <div class="info-card-head">
                    <div>
                        <strong>${item.name}</strong>
                        <small>${item.username}</small>
                    </div>
                    ${statusChip(item.is_active ? "active" : "inactive")}
                </div>
                <div class="info-grid">
                    <span>Konum: ${formatCoord(item.lat, item.lon)}</span>
                    <span>Önleyici: ${item.assigned_interceptor_drone_uid || "-"}</span>
                    <span>Kullanıcı Kimliği: ${item.user_id}</span>
                </div>
            </article>
        `).join("");
    }

    function renderFieldLayers(fieldLayers) {
        if (!fieldLayersList) {
            return;
        }
        if (!fieldLayers.length) {
            fieldLayersList.innerHTML = '<div class="empty-state">Saha katmanı yok.</div>';
            return;
        }

        fieldLayersList.innerHTML = fieldLayers.map((item) => {
            const color = fieldLayerDisplayColor(item);
            const ring = item.geometry && Array.isArray(item.geometry.coordinates) && Array.isArray(item.geometry.coordinates[0])
                ? item.geometry.coordinates[0]
                : [];
            return `
                <article class="info-card field-layer-card ${selectedFieldLayerId === item.id ? "selected" : ""}" style="--field-layer-color: ${color}" data-field-layer-focus-id="${item.id}" role="button" tabindex="0" title="Haritada bu katmana git">
                    <div class="info-card-head">
                        <div>
                            <strong>${item.name}</strong>
                            <small>${fieldLayerLabel(item.layer_type)} / ${Math.max(0, ring.length - 1)} nokta / Haritada git</small>
                        </div>
                        <div class="card-actions">
                            <span class="status-chip active">Aktif</span>
                            ${readonly ? "" : `<button type="button" class="danger-btn" data-field-layer-delete-id="${item.id}">Sil</button>`}
                        </div>
                    </div>
                    <div class="field-layer-swatch"></div>
                </article>
            `;
        }).join("");

        fieldLayersList.querySelectorAll("[data-field-layer-focus-id]").forEach((card) => {
            card.addEventListener("click", () => {
                selectedFieldLayerId = card.getAttribute("data-field-layer-focus-id");
                selectedDetectionId = null;
                selectedTaskId = null;
                renderFieldLayers(latestState.fieldLayers);
                renderDetections(latestState.detections);
                renderTasks(latestState.tasks);
                refreshMap();
            });
            card.addEventListener("keydown", (event) => {
                if (event.key !== "Enter" && event.key !== " ") {
                    return;
                }
                event.preventDefault();
                card.click();
            });
        });
        if (readonly) {
            return;
        }
        fieldLayersList.querySelectorAll("[data-field-layer-delete-id]").forEach((button) => {
            button.addEventListener("click", async (event) => {
                event.stopPropagation();
                const layerId = button.getAttribute("data-field-layer-delete-id");
                const layer = latestState.fieldLayers.find((item) => item.id === layerId);
                if (!layerId || !layer) {
                    return;
                }
                if (!window.confirm(`${layer.name} saha katmanı silinsin mi?`)) {
                    return;
                }
                try {
                    button.disabled = true;
                    await fetchJson(`/v1/field-layers/${encodeURIComponent(layerId)}`, { method: "DELETE" });
                    if (selectedFieldLayerId === layerId) {
                        selectedFieldLayerId = null;
                    }
                    showFlash(`${layer.name} saha katmanı silindi.`, false);
                    await refreshAll();
                } catch (error) {
                    button.disabled = false;
                    showFlash(`Saha katmanı silinemedi: ${error.message}`, true);
                }
            });
        });
    }

    function renderDemoCredentials(operators, reconDroneUid) {
        if (!demoCredentialsNode) {
            return;
        }
        if (!operators || !operators.length) {
            demoCredentialsNode.innerHTML = "";
            return;
        }

        demoCredentialsNode.innerHTML = `
            <article class="info-card">
                <div class="info-card-head">
                    <div>
                        <strong>Demo Giriş Bilgileri</strong>
                        <small>Keşif: ${reconDroneUid}</small>
                    </div>
                    ${statusChip("active")}
                </div>
                <div class="info-grid">
                    ${operators.map((item) => `${item.username} / ${item.password} / ${item.interceptor_drone_uid} / ${item.station_name}`).map((line) => `<span>${line}</span>`).join("")}
                </div>
                <div class="info-grid">
                    <span>Operatör paneli: /ui/operator</span>
                    <span>Sunum modu: aynı tarayıcıda admin önizlemesi kullanılabilir.</span>
                </div>
            </article>
        `;
    }

    function setDemoDetectionMessage(message, isError) {
        if (!demoLastDetectionNode) {
            return;
        }
        demoLastDetectionNode.className = isError ? "error-box" : "success-box";
        demoLastDetectionNode.innerHTML = message;
    }

    function renderTasks(tasks) {
        document.getElementById("metric-task-total").textContent = String(tasks.length);
        const pendingCount = tasks.filter((item) => item.status === "pending").length;
        const acceptedCount = tasks.filter((item) => item.status === "accepted").length;
        document.getElementById("metric-task-breakdown").textContent = `Beklemede ${pendingCount} / Kabul ${acceptedCount}`;

        if (!tasks.length) {
            tasksList.innerHTML = '<div class="empty-state">Angajman görevi yok.</div>';
            return;
        }

        const orderedTasks = tasks.slice().sort(compareByFieldLayerEffect);
        tasksList.innerHTML = orderedTasks.map((item) => `
            <button type="button" class="task-card ${selectedTaskId === item.id ? "selected" : ""} ${fieldLayerEffectCardClass(item)}" data-task-id="${item.id}">
                <div class="info-card-head">
                    <div>
                        <strong>${item.contact_id}</strong>
                        <small>${item.operator_station_name} / ${item.operator_username}</small>
                    </div>
                    ${statusChip(item.status)}
                </div>
                ${renderFieldLayerEffectBadges(item)}
                <div class="info-grid">
                    <span>Önleyici: ${item.interceptor_drone_uid}</span>
                    <span>Hedef: ${formatCoord(item.target_lat, item.target_lon)}</span>
                    <span>Atama: ${formatTime(item.assigned_at)}</span>
                    <span>Not: ${item.operator_note || "-"}</span>
                </div>
            </button>
        `).join("");

        tasksList.querySelectorAll("[data-task-id]").forEach((button) => {
            button.addEventListener("click", () => {
                selectedTaskId = button.getAttribute("data-task-id");
                selectedFieldLayerId = null;
                const linkedTask = latestState.tasks.find((task) => task.id === selectedTaskId);
                selectedDetectionId = linkedTask ? linkedTask.hostile_detection_id : null;
                renderTasks(latestState.tasks);
                renderDetections(latestState.detections);
                refreshMap();
                syncReplayTask();
            });
        });
    }

    async function refreshAll() {
        clearFlash();
        try {
            const [tracks, detections, stations, tasks, fieldLayers] = await Promise.all([
                fetchJson("/v1/tracks"),
                fetchJson("/v1/hostile-detections"),
                fetchJson("/v1/operator-stations"),
                fetchJson("/v1/intercept-tasks"),
                fetchJson("/v1/field-layers")
            ]);
            latestState = { tracks, detections, stations, tasks, fieldLayers, aircraft: latestState.aircraft };
            syncMapCreatedTargets(detections);
            renderTracks(tracks);
            renderDetections(detections);
            renderStations(stations);
            renderFieldLayers(fieldLayers);
            renderTasks(tasks);
            updateDemoFlowState();
            refreshMap();
            syncReplayTask();
            refreshAirTraffic();
        } catch (error) {
            showFlash(`Panel verileri alınamadı: ${error.message}`, true);
        }
    }

    if (stationForm && !readonly) {
        stationForm.addEventListener("submit", async (event) => {
            event.preventDefault();
            clearFlash();
            const payload = {
                user_id: document.getElementById("station-user-id").value.trim(),
                name: document.getElementById("station-name").value.trim(),
                lat: Number(document.getElementById("station-lat").value),
                lon: Number(document.getElementById("station-lon").value),
                assigned_interceptor_drone_id: document.getElementById("station-drone-id").value.trim() || null,
                is_active: document.getElementById("station-active").checked
            };
            try {
                await fetchJson("/v1/operator-stations", {
                    method: "POST",
                    body: JSON.stringify(payload)
                });
                stationForm.reset();
                document.getElementById("station-active").checked = true;
                showFlash("Operatör istasyonu kaydedildi.", false);
                await refreshAll();
            } catch (error) {
                showFlash(`İstasyon kaydı başarısız: ${error.message}`, true);
            }
        });
    }

    if (demoResetButton && !readonly) {
        demoResetButton.addEventListener("click", async () => {
            clearFlash();
            setDemoResetResult("Demo kayıtları sıfırlanıyor...", false);
            try {
                const result = await fetchJson("/v1/demo/reset", { method: "POST", body: JSON.stringify({}) });
                selectedDetectionId = null;
                selectedTaskId = null;
                draftMapTarget = null;
                draftMapContactId = "";
                mapCreatedTargets = [];
                mapTargetSequence = 0;
                setMapTargetPickEnabled(false);
                if (demoCredentialsNode) {
                    demoCredentialsNode.innerHTML = "";
                }
                if (demoLastDetectionNode) {
                    demoLastDetectionNode.className = "empty-state";
                    demoLastDetectionNode.textContent = "Demo tespiti oluşturulduğunda burada en yakın operatör bilgisi gösterilir.";
                }
                setDemoResetResult(result.message || "Demo kayıtları sıfırlandı.", false);
                showFlash("Demo temiz başlangıç durumuna alındı.", false);
                await refreshAll();
            } catch (error) {
                setDemoResetResult(`Demo sıfırlanamadı: ${error.message}`, true);
                showFlash(`Demo sıfırlanamadı: ${error.message}`, true);
            }
        });
    }

    if (demoScenarioForm && !readonly) {
        demoScenarioForm.addEventListener("submit", async (event) => {
            event.preventDefault();
            clearFlash();
            setDemoStepState("scenario", "active");
            const payload = {
                recon_lat: Number(document.getElementById("demo-recon-lat").value),
                recon_lon: Number(document.getElementById("demo-recon-lon").value),
                recon_alt_m: Number(document.getElementById("demo-recon-alt").value),
                recon_heading_deg: Number(document.getElementById("demo-recon-heading").value),
                stations: [1, 2, 3].map((index) => ({
                    name: document.getElementById(`demo-station-${index}-name`).value.trim(),
                    lat: Number(document.getElementById(`demo-station-${index}-lat`).value),
                    lon: Number(document.getElementById(`demo-station-${index}-lon`).value)
                }))
            };
            try {
                const result = await fetchJson("/v1/demo/scenario", {
                    method: "POST",
                    body: JSON.stringify(payload)
                });
                renderDemoCredentials(result.operators || [], result.recon_drone_uid);
                selectedDetectionId = null;
                selectedTaskId = null;
                setDemoStepState("scenario", "done");
                showFlash("Demo senaryo kuruldu. Operatör paneli için demo_operator_1..3 kullanabilirsin.", false);
                await refreshAll();
            } catch (error) {
                setDemoStepState("scenario", "idle");
                showFlash(`Demo senaryo kurulamadı: ${error.message}`, true);
            }
        });
    }

    if (demoDetectionForm && !readonly) {
        demoDetectionForm.addEventListener("submit", async (event) => {
            event.preventDefault();
            clearFlash();
            setDemoStepState("detection", "active");
            setDemoDetectionMessage("Demo hedef tespiti oluşturuluyor...", false);
            const payload = {
                contact_id: document.getElementById("demo-contact-id").value.trim(),
                target_lat: Number(document.getElementById("demo-target-lat").value),
                target_lon: Number(document.getElementById("demo-target-lon").value),
                target_alt_m: Number(document.getElementById("demo-target-alt").value),
                confidence: Number(document.getElementById("demo-confidence").value)
            };
            try {
                const result = await fetchJson("/v1/demo/detections", {
                    method: "POST",
                    body: JSON.stringify(payload)
                });
                if (demoLastDetectionNode) {
                    demoLastDetectionNode.className = "detail-grid";
                    demoLastDetectionNode.innerHTML = `
                        <div class="detail-item"><strong>Temas</strong><span>${result.detection.contact_id}</span></div>
                        <div class="detail-item"><strong>Atanan İstasyon</strong><span>${result.assigned_station_name || "-"}</span></div>
                        <div class="detail-item"><strong>Operatör</strong><span>${result.assigned_operator_username || "-"}</span></div>
                        <div class="detail-item"><strong>Görev</strong><span>${result.assigned_task_id || "-"}</span></div>
                    `;
                }
                selectedDetectionId = result.detection.id;
                selectedTaskId = result.assigned_task_id || null;
                setDemoStepState("detection", "done");
                setDemoStepState("operator", "active");
                showFlash("Demo hedef tespiti oluşturuldu ve en yakın operatör seçildi.", false);
                await refreshAll();
            } catch (error) {
                setDemoStepState("detection", "idle");
                setDemoDetectionMessage(`Demo tespit oluşturulamadı: ${error.message}`, true);
                showFlash(`Demo tespit oluşturulamadı: ${error.message}`, true);
            }
        });
    }

    if (demoOpenOperatorButton) {
        demoOpenOperatorButton.addEventListener("click", () => {
            setDemoStepState("operator", "done");
            window.open("/ui/operator", "_blank", "noopener");
        });
    }

    if (toggleMapTargetPickButton && !readonly) {
        toggleMapTargetPickButton.addEventListener("click", () => {
            if (mapTargetPickLoading) {
                return;
            }
            clearFlash();
            if (draftMapTarget) {
                showFlash("Hedef noktası seçili. Kaydetmek için Hedefi Onayla düğmesine basın ya da haritada başka bir nokta seçin.", false);
                return;
            }
            if (mapTargetPickEnabled) {
                showFlash("Hedef ekleme modu açık. Hedef tespiti oluşturmak için haritada bir noktaya tıklayın.", false);
                return;
            }
            setMapTargetPickEnabled(true);
            showFlash("Hedef ekleme modu açıldı. Hedef oluşturmak için haritada bir noktaya tıklayın.", false);
        });
        updateMapTargetPickButton();
    }

    if (confirmMapTargetButton && !readonly) {
        confirmMapTargetButton.addEventListener("click", confirmMapTargetSelection);
    }

    if (cancelMapTargetButton && !readonly) {
        cancelMapTargetButton.addEventListener("click", () => {
            cancelMapTargetSelection("Hedef seçimi iptal edildi.");
        });
    }

    if (fieldLayerDrawStartButton && !readonly) {
        fieldLayerDrawStartButton.addEventListener("click", () => {
            clearFlash();
            setFieldLayerDrawingEnabled(!fieldLayerDrawingEnabled);
            showFlash(
                fieldLayerDrawingEnabled
                    ? "Saha katmanı çizimi açıldı. Haritada sol tıkla alan seçin, sağ tıkla sürükleyerek dolaşın."
                    : "Saha katmanı çizimi duraklatıldı.",
                false
            );
        });
    }

    if (fieldLayerCancelButton && !readonly) {
        fieldLayerCancelButton.addEventListener("click", () => {
            clearFieldLayerDraft();
            showFlash("Saha katmanı çizimi iptal edildi.", false);
        });
    }

    if (fieldLayerForm && !readonly) {
        fieldLayerForm.addEventListener("submit", saveFieldLayer);
    }

    if (fieldLayerTypeInput && !readonly) {
        fieldLayerTypeInput.addEventListener("change", () => {
            renderFieldLayerColorControls(true);
            refreshMap();
        });
    }

    if (fieldLayerColorPalette && !readonly) {
        fieldLayerColorPalette.addEventListener("click", (event) => {
            const button = event.target.closest("[data-field-layer-color]");
            if (!button || !fieldLayerColorInput) {
                return;
            }
            const color = normalizeFieldLayerColor(button.getAttribute("data-field-layer-color"));
            if (!color) {
                return;
            }
            fieldLayerColorInput.value = color;
            renderFieldLayerColorControls(false);
            refreshMap();
        });
    }

    if (fieldLayerColorInput && !readonly) {
        fieldLayerColorInput.addEventListener("input", () => {
            renderFieldLayerColorControls(false);
            refreshMap();
        });
    }

    renderFieldLayerColorControls(true);
    updateFieldLayerDraftUi();

    if (replaySlider) {
        replaySlider.addEventListener("input", () => {
            stopReplayTimer();
            setReplayCursorFromSlider();
        });
    }

    if (replayPlayButton) {
        replayPlayButton.addEventListener("click", toggleReplayPlayback);
    }

    if (replaySpeedSelect) {
        replaySpeedSelect.addEventListener("change", updateReplayControls);
    }
    updateReplayControls();

    if (toggleAirTrafficButton) {
        toggleAirTrafficButton.addEventListener("click", async () => {
            airTrafficEnabled = !airTrafficEnabled;
            airTrafficLastError = "";
            if (!airTrafficEnabled) {
                latestState.aircraft = [];
                updateAirTrafficButton();
                refreshMap();
                return;
            }
            updateAirTrafficButton();
            await refreshAirTraffic();
        });
        updateAirTrafficButton();
    }

    const refreshButton = document.getElementById("refresh-control-center");
    if (refreshButton) {
        refreshButton.addEventListener("click", refreshAll);
    }

    refreshAll();
    window.setInterval(refreshAll, 5000);
})();
