(function () {
    const root = document.querySelector('[data-page="operator"]');
    if (!root) {
        return;
    }

    const csrfToken = document.body.dataset.csrfToken || "";
    const csrfCookieName = document.body.dataset.csrfCookieName || "fd_csrf_token";
    const listNode = document.getElementById("operator-task-list");
    const detailNode = document.getElementById("operator-task-detail");
    const actionForm = document.getElementById("operator-action-form");
    const noteField = document.getElementById("operator-note");
    const flashNode = document.getElementById("operator-flash-message");
    const mapSummaryNode = document.getElementById("operator-map-summary");
    const mapFocusNode = document.getElementById("operator-map-focus");
    const replayTitle = document.getElementById("operator-replay-title");
    const replayClock = document.getElementById("operator-replay-clock");
    const replaySlider = document.getElementById("operator-replay-slider");
    const replayPlayButton = document.getElementById("operator-replay-play");
    const replaySpeedSelect = document.getElementById("operator-replay-speed");
    const replayStatus = document.getElementById("operator-replay-status");
    const progressPanel = document.getElementById("operator-progress-panel");
    const mapController = window.HavaMap ? window.HavaMap.createMap({
        canvasId: "operator-map-canvas",
        emptyMessage: "Seçili görev için harita verisi bekleniyor.",
        fitOnEveryUpdate: false
    }) : null;

    let currentTask = null;
    let taskCache = [];
    let trackCache = [];
    let stationCache = [];
    let playbackCache = [];
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

    const STATUS_LABELS = {
        pending: "Beklemede",
        accepted: "Kabul Edildi",
        completed: "Tamamlandı",
        rejected: "Reddedildi",
        cancelled: "İptal",
        expired: "Süre Doldu",
        assigned: "Atanmış",
        resolved: "İmha Edildi"
    };

    const ACTION_LABELS = {
        accept: "kabul",
        reject: "ret",
        complete: "tamamlama"
    };

    function showFlash(message, isError) {
        flashNode.hidden = false;
        flashNode.textContent = message;
        flashNode.classList.toggle("error-box", Boolean(isError));
        flashNode.classList.toggle("success-box", !isError);
    }

    function clearFlash() {
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

    function formatTime(value) {
        if (!value) {
            return "-";
        }
        return new Date(value).toLocaleString("tr-TR");
    }

    function formatCoord(lat, lon) {
        return `${Number(lat).toFixed(5)}, ${Number(lon).toFixed(5)}`;
    }

    function statusLabel(value) {
        const clean = String(value || "").toLowerCase();
        return STATUS_LABELS[clean] || String(value || "-");
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

    function renderProgressPanel(task) {
        if (!progressPanel) {
            return;
        }
        if (!task || !window.HavaMap) {
            progressPanel.className = "progress-panel empty-state";
            progressPanel.textContent = "Aktif görev seçildiğinde kalan mesafe, ETA ve ilerleme burada gösterilir.";
            return;
        }
        const station = stationCache.find((item) => item.id === task.operator_station_id) || null;
        const track = trackCache.find((item) => item.drone_uid === task.interceptor_drone_uid) || null;
        const total = station
            ? window.HavaMap.distanceMeters(station.lat, station.lon, task.target_lat, task.target_lon)
            : Number(task.range_m || 0);
        const remaining = track
            ? window.HavaMap.distanceMeters(track.lat, track.lon, task.target_lat, task.target_lon)
            : null;
        const progress = remaining === null || total <= 0
            ? 0
            : Math.max(0, Math.min(100, ((total - remaining) / total) * 100));
        const speed = track ? Number(track.speed_mps || 0) : 0;
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

    function renderCounters(tasks) {
        document.getElementById("operator-pending-count").textContent = String(tasks.filter((item) => item.status === "pending").length);
        document.getElementById("operator-accepted-count").textContent = String(tasks.filter((item) => item.status === "accepted").length);
        document.getElementById("operator-completed-count").textContent = String(tasks.filter((item) => item.status === "completed").length);
    }

    function updateMap() {
        if (!mapController) {
            return;
        }
        if (!currentTask) {
            mapController.setState({
                tracks: [],
                detections: [],
            stations: [],
            tasks: [],
            playbackPoints: [],
            playbackTracks: [],
            replayEvents: [],
            focus: {}
        });
            mapSummaryNode.textContent = "Seçili görev için harita hazır değil.";
            mapFocusNode.textContent = "Önleyici telemetrisi geldikçe hedefe yaklaşma burada canlı izlenir.";
            return;
        }

        const relatedTrack = trackCache.find((item) => item.drone_uid === currentTask.interceptor_drone_uid) || null;
        const relatedStation = stationCache.find((item) => item.id === currentTask.operator_station_id) || null;
        const relatedRecon = trackCache.find((item) => item.drone_uid === currentTask.recon_drone_uid) || null;
        const detections = [{
            id: currentTask.hostile_detection_id,
            contact_id: currentTask.contact_id,
            target_lat: currentTask.target_lat,
            target_lon: currentTask.target_lon,
            target_alt_m: currentTask.target_alt_m,
            status: currentTask.status === "completed" ? "resolved" : "assigned"
        }];

        mapController.setState({
            tracks: [relatedTrack, relatedRecon].filter(Boolean),
            detections,
            stations: relatedStation ? [relatedStation] : [],
            tasks: [currentTask],
            playbackPoints: playbackCache,
            playbackTracks: replayState.tracks,
            replayCursor: replayState.cursorTime ? new Date(replayState.cursorTime).toISOString() : null,
            replayEvents: replayState.events,
            focus: {
                taskId: currentTask.id,
                detectionId: currentTask.hostile_detection_id
            }
        });

        mapSummaryNode.textContent = relatedTrack
            ? `${currentTask.interceptor_drone_uid} canlı konumda. Son görülme ${formatTime(relatedTrack.last_seen_at)}.`
            : `${currentTask.interceptor_drone_uid} için henüz canlı telemetri yok.`;

        if (relatedTrack && window.HavaMap) {
            const remaining = window.HavaMap.distanceMeters(
                relatedTrack.lat,
                relatedTrack.lon,
                currentTask.target_lat,
                currentTask.target_lon
            );
            mapFocusNode.textContent = currentTask.status === "completed"
                ? `${currentTask.contact_id} hedefi imha edildi. Önleyici son görev noktasında.`
                : `${currentTask.contact_id} hedefi için kalan yaklaşık mesafe ${Math.round(remaining)} m.`;
        } else {
            mapFocusNode.textContent = currentTask.status === "completed"
                ? `${currentTask.contact_id} hedefi imha edildi.`
                : `${currentTask.contact_id} hedefi ${formatCoord(currentTask.target_lat, currentTask.target_lon)} koordinatında bekleniyor.`;
        }
    }

    function renderDetail(task) {
        if (!task) {
            detailNode.className = "empty-state";
            detailNode.innerHTML = "Bir görev seçildiğinde mutlak hedef koordinatı, yönelim ve menzil bilgileri burada gösterilir.";
            actionForm.hidden = true;
            renderProgressPanel(null);
            updateMap();
            return;
        }

        const relatedTrack = trackCache.find((item) => item.drone_uid === task.interceptor_drone_uid) || null;
        const remaining = relatedTrack && window.HavaMap
            ? window.HavaMap.distanceMeters(relatedTrack.lat, relatedTrack.lon, task.target_lat, task.target_lon)
            : null;

        detailNode.className = "detail-grid";
        detailNode.innerHTML = `
            <div class="detail-item"><strong>Temas</strong><span>${task.contact_id}</span></div>
            <div class="detail-item"><strong>Keşif</strong><span>${task.recon_drone_uid}</span></div>
            <div class="detail-item"><strong>Önleyici</strong><span>${task.interceptor_drone_uid}</span></div>
            <div class="detail-item"><strong>İstasyon</strong><span>${task.operator_station_name}</span></div>
            <div class="detail-item"><strong>Hedef</strong><span>${formatCoord(task.target_lat, task.target_lon)}</span></div>
            <div class="detail-item"><strong>Alt</strong><span>${Number(task.target_alt_m).toFixed(1)} m</span></div>
            <div class="detail-item"><strong>Yönelim</strong><span>${Number(task.bearing_mil).toFixed(1)} mil / ${Number(task.true_bearing_deg).toFixed(1)}°</span></div>
            <div class="detail-item"><strong>Menzil</strong><span>${Number(task.range_m).toFixed(1)} m</span></div>
            <div class="detail-item"><strong>Yükseliş</strong><span>${Number(task.elevation_mil).toFixed(1)} mil</span></div>
            <div class="detail-item"><strong>Güven</strong><span>${task.confidence}</span></div>
            <div class="detail-item"><strong>Atama</strong><span>${formatTime(task.assigned_at)}</span></div>
            <div class="detail-item"><strong>Kalan Mesafe</strong><span>${remaining === null ? "-" : `${Math.round(remaining)} m`}</span></div>
            <div class="detail-item"><strong>Durum</strong><span>${statusLabel(task.status)}</span></div>
        `;

        actionForm.hidden = false;
        noteField.value = task.operator_note || "";

        const buttons = actionForm.querySelectorAll("[data-action]");
        buttons.forEach((button) => {
            const action = button.getAttribute("data-action");
            let disabled = false;
            if (action === "accept") {
                disabled = task.status !== "pending";
            } else if (action === "reject") {
                disabled = !["pending", "accepted"].includes(task.status);
            } else if (action === "complete") {
                disabled = !["pending", "accepted"].includes(task.status);
            }
            button.disabled = disabled;
        });

        updateMap();
        renderProgressPanel(task);
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
        if (replayTitle) {
            replayTitle.textContent = currentTask ? `${currentTask.contact_id} / ${currentTask.interceptor_drone_uid}` : "Görev seçilmedi";
        }
        if (replayClock) {
            replayClock.textContent = hasReplay ? new Date(replayState.cursorTime).toLocaleTimeString("tr-TR") : "--:--:--";
        }
        if (replayStatus) {
            if (!currentTask) {
                replayStatus.textContent = "Replay için görev seçin.";
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
        playbackCache = [];
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
        updateMap();
    }

    function setReplayCursorFromSlider() {
        if (replayState.minTime === null || replayState.maxTime === null || !replaySlider) {
            return;
        }
        const percent = Number(replaySlider.value) / 1000;
        replayState.cursorTime = replayState.minTime + (replayState.maxTime - replayState.minTime) * percent;
        updateReplayControls();
        updateMap();
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
            updateMap();
        }, 500);
        updateReplayControls();
    }

    async function refreshPlayback() {
        if (!currentTask) {
            clearReplay();
            return;
        }
        if (replayState.taskId === currentTask.id && replayState.tracks.length) {
            replayState.events = replayEventMarkers(currentTask);
            updateReplayControls();
            updateMap();
            return;
        }
        stopReplayTimer();
        replayState.taskId = currentTask.id;
        replayState.tracks = [];
        replayState.events = replayEventMarkers(currentTask);
        replayState.minTime = null;
        replayState.maxTime = null;
        replayState.cursorTime = null;
        updateReplayControls();
        try {
            const taskId = currentTask.id;
            const [recon, interceptor] = await Promise.all([
                fetchJson(`/v1/tracks/${encodeURIComponent(currentTask.recon_drone_uid)}/playback?minutes=60`),
                fetchJson(`/v1/tracks/${encodeURIComponent(currentTask.interceptor_drone_uid)}/playback?minutes=60`)
            ]);
            if (!currentTask || currentTask.id !== taskId) {
                return;
            }
            const tracks = [
                { drone_uid: currentTask.recon_drone_uid, platform_role: "recon", points: recon.points || [] },
                { drone_uid: currentTask.interceptor_drone_uid, platform_role: "interceptor", points: interceptor.points || [] }
            ];
            const times = collectReplayTimes(tracks, replayState.events);
            playbackCache = interceptor.points || [];
            replayState.tracks = tracks;
            replayState.minTime = times.length ? times[0] : null;
            replayState.maxTime = times.length ? times[times.length - 1] : null;
            replayState.cursorTime = replayState.maxTime;
        } catch (_error) {
            playbackCache = [];
        }
        updateReplayControls();
        updateMap();
    }

    function renderList(tasks) {
        renderCounters(tasks);
        if (!tasks.length) {
            listNode.innerHTML = '<div class="empty-state">Aktif görev yok.</div>';
            currentTask = null;
            renderDetail(null);
            return;
        }

        if (!currentTask || !tasks.some((item) => item.id === currentTask.id)) {
            currentTask = tasks[0];
        } else {
            currentTask = tasks.find((item) => item.id === currentTask.id) || tasks[0];
        }

        listNode.innerHTML = tasks.map((task) => `
            <button type="button" class="task-card ${currentTask && currentTask.id === task.id ? "selected" : ""}" data-task-id="${task.id}">
                <strong>${task.contact_id}</strong>
                <span>${task.operator_station_name}</span>
                <small>${statusLabel(task.status)} / ${task.interceptor_drone_uid}</small>
            </button>
        `).join("");

        listNode.querySelectorAll("[data-task-id]").forEach((button) => {
            button.addEventListener("click", async () => {
                const taskId = button.getAttribute("data-task-id");
                currentTask = taskCache.find((item) => item.id === taskId) || null;
                renderList(taskCache);
                renderDetail(currentTask);
                await refreshPlayback();
            });
        });

        renderDetail(currentTask);
    }

    async function refreshTasks() {
        clearFlash();
        try {
            const [tasks, tracks, stations] = await Promise.all([
                fetchJson("/v1/intercept-tasks/me"),
                fetchJson("/v1/tracks"),
                fetchJson("/v1/operator-stations")
            ]);
            taskCache = tasks;
            trackCache = tracks;
            stationCache = stations;
            renderList(taskCache);
            await refreshPlayback();
        } catch (error) {
            showFlash(`Görevler alınamadı: ${error.message}`, true);
        }
    }

    async function sendAction(action) {
        if (!currentTask) {
            return;
        }
        clearFlash();
        try {
            const updated = await fetchJson(`/v1/intercept-tasks/${encodeURIComponent(currentTask.id)}/${action}`, {
                method: "POST",
                body: JSON.stringify({ operator_note: noteField.value.trim() || null })
            });
            currentTask = updated;
            showFlash(`Görev ${ACTION_LABELS[action] || "işlem"} işlemi başarılı.`, false);
            await refreshTasks();
        } catch (error) {
            showFlash(`Görev işlemi başarısız: ${error.message}`, true);
        }
    }

    actionForm.querySelectorAll("[data-action]").forEach((button) => {
        button.addEventListener("click", () => {
            const action = button.getAttribute("data-action");
            sendAction(action);
        });
    });

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

    const refreshButton = document.getElementById("refresh-operator-panel");
    if (refreshButton) {
        refreshButton.addEventListener("click", refreshTasks);
    }

    refreshTasks();
    window.setInterval(refreshTasks, 5000);
})();
