(function () {
    const unitClassSelect = document.getElementById("unit_class");
    const droneUidInput = document.getElementById("drone_uid");
    if (!unitClassSelect || !droneUidInput) {
        return;
    }

    async function refreshSuggestedUid() {
        const selected = unitClassSelect.value;
        if (!selected) {
            return;
        }
        try {
            const response = await fetch(`/ui/drones/next-uid?unit_class=${encodeURIComponent(selected)}`, {
                method: "GET",
                credentials: "same-origin",
                headers: { Accept: "application/json" }
            });
            if (!response.ok) {
                return;
            }
            const data = await response.json();
            if (data && typeof data.drone_uid === "string" && data.drone_uid.length > 0) {
                droneUidInput.value = data.drone_uid;
            }
        } catch (_error) {
            // Keep current value; user can retry with page refresh.
        }
    }

    unitClassSelect.addEventListener("change", () => {
        refreshSuggestedUid();
    });
})();
