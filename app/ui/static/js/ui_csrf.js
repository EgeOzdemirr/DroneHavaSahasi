(function () {
    function readCookie(name) {
        const prefix = `${name}=`;
        const match = document.cookie.split("; ").find((item) => item.startsWith(prefix));
        return match ? decodeURIComponent(match.slice(prefix.length)) : "";
    }

    function syncCsrfFields() {
        const cookieName = document.body.dataset.csrfCookieName || "fd_csrf_token";
        const token = readCookie(cookieName) || document.body.dataset.csrfToken || "";
        if (!token) {
            return;
        }

        document.querySelectorAll('input[type="hidden"][name="csrf_token"]').forEach((field) => {
            field.value = token;
        });
        document.body.dataset.csrfToken = token;
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", syncCsrfFields, { once: true });
    } else {
        syncCsrfFields();
    }

    document.addEventListener("submit", () => {
        syncCsrfFields();
    }, true);
})();
