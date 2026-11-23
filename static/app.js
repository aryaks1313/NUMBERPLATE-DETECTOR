"use strict";



let currentUser = null;
let monitorTimer = null;
let notificationTimer = null;
let currentSection = "overview";

const $ = (id) => document.getElementById(id);

async function api(url, options = {}) {
    const config = {
        credentials: "same-origin",
        ...options,
        headers: {
            ...(options.headers || {})
        }
    };


    if (options.body && !(options.body instanceof FormData)) {
        config.headers["Content-Type"] = "application/json";
    }

    const response = await fetch(url, config);
    const contentType = response.headers.get("content-type") || "";

    let result;

    if (contentType.includes("application/json")) {
        result = await response.json();
    } else {
        result = await response.text();
    }

    if (response.status === 401) {
        window.location.href = "/";
        throw new Error("Your session has expired. Please log in again.");
    }

    if (!response.ok) {
        const message =
            typeof result === "object"
                ? result.detail || result.message || "Request failed."
                : result || "Request failed.";

        throw new Error(message);
    }

    return result;
}

function showMessage(elementId, message, type = "success") {
    const element = $(elementId);
    if (!element) return;

    element.textContent = message;
    element.className = `message ${type}`;
    element.hidden = false;
}

function hideMessage(elementId) {
    const element = $(elementId);
    if (element) element.hidden = true;
}

function escapeHtml(value) {
    return String(value ?? "").replace(/[&<>"']/g, (character) => ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#039;"
    })[character]);
}

function formatDate(value) {
    if (!value) return "—";

    const date = new Date(`${value}T00:00:00`);

    if (Number.isNaN(date.getTime())) return value;

    return date.toLocaleDateString("en-IN", {
        day: "2-digit",
        month: "short",
        year: "numeric"
    });
}

function formatTime(value) {
    if (!value) return "—";

    const match = String(value).match(/^(\d{1,2}):(\d{2})/);

    if (!match) return value;

    const date = new Date();
    date.setHours(Number(match[1]), Number(match[2]), 0, 0);

    return date.toLocaleTimeString("en-IN", {
        hour: "2-digit",
        minute: "2-digit"
    });
}

function statusClass(status) {
    const value = String(status || "").toLowerCase();

    if (value.includes("unmatch") || value.includes("walk_in") || value.includes("pending") || value.includes("scheduled")) {
        return "warning";
    }

    if (value.includes("match") || value.includes("confirm") || value.includes("success")) {
        return "success";
    }

    if (value.includes("error") || value.includes("fail")) {
        return "danger";
    }

    return "neutral";
}

function showPage(sectionName) {
    const section = $(`${sectionName}Section`);
    if (!section || section.hidden) return;

    document.querySelectorAll(".page-section").forEach((page) => {
        page.classList.remove("active");
    });

    document.querySelectorAll(".nav-item").forEach((button) => {
        button.classList.toggle(
            "active",
            button.dataset.section === sectionName
        );
    });

    section.classList.add("active");
    currentSection = sectionName;

    const titles = {
        overview: "Overview",
        booking: "Register Booking",
        bookings: "My Bookings",
        video: "Video Processing",
        monitor: "Live Gate Monitor",
        advisors: "Service Advisors",
        notifications: "Notifications"
    };

    $("pageTitle").textContent = titles[sectionName] || "Dashboard";

    if (sectionName === "bookings") loadBookings();
    if (sectionName === "notifications") loadNotifications();
    if (sectionName === "advisors") loadAdvisors();
    if (sectionName === "monitor") loadMonitorStatus();
    if (sectionName === "overview") loadDashboard();
}



async function initializeApp() {
    try {
        currentUser = await api("/api/me");

        if (!currentUser || !currentUser.role) {
            throw new Error("User session information is missing.");
        }

        const isAdmin = currentUser.role === "admin";

        $("welcomeName").textContent =
            currentUser.name || currentUser.username || "User";

        $("roleBadge").textContent =
            isAdmin ? "Administrator" : "Service Advisor";

        $("userAvatar").textContent =
            (currentUser.name || currentUser.username || "CS")
                .substring(0, 2)
                .toUpperCase();


        document.querySelectorAll(".admin-only").forEach((element) => {
            element.hidden = !isAdmin;
        });

        if (!isAdmin) {
            $("bookingPageDescription").textContent =
                "View bookings assigned to your advisor account.";
        }


        const dateInput = document.querySelector('[name="booking_date"]');

        if (dateInput) {
            const today = new Date();
            const localDate = [
                today.getFullYear(),
                String(today.getMonth() + 1).padStart(2, "0"),
                String(today.getDate()).padStart(2, "0")
            ].join("-");

            dateInput.value = localDate;
        }

        if (isAdmin) {
            await loadAdvisorsForBooking();
        }

        await loadDashboard();
        await loadBookings();
        await loadNotifications();

        if (isAdmin) {
            await loadMonitorStatus();
        }

        startBackgroundRefresh();

        showPage("overview");

    } catch (error) {
        console.error("Initialization error:", error);
        showGlobalError(error.message);
    }
}

function showGlobalError(message) {
    const element = $("globalMessage");

    if (!element) return;

    element.textContent = message;
    element.className = "message error";
    element.hidden = false;
}



document.querySelectorAll(".nav-item").forEach((button) => {
    button.addEventListener("click", () => {
        showPage(button.dataset.section);
    });
});

document.querySelectorAll("[data-go]").forEach((button) => {
    button.addEventListener("click", () => {
        showPage(button.dataset.go);
    });
});



async function loadDashboard() {
    try {
        const endpoint =
            currentUser?.role === "admin"
                ? "/api/admin/dashboard"
                : "/api/advisor/dashboard";

        const data = await api(endpoint);

        /*
          Expected dashboard values:
          {
            total_bookings: 10,
            today_bookings: 4,
            total_detections: 8,
            total_notifications: 3
          }

          If your backend uses different field names,
          update the mapping below.
        */

        $("statOne").textContent =
            data.total_bookings ?? data.totalBookings ?? 0;

        $("statTwo").textContent =
            data.today_bookings ?? data.todayBookings ?? 0;

        $("statThree").textContent =
            data.total_detections ?? data.totalDetections ?? 0;

        $("statFour").textContent =
            data.total_notifications ?? data.totalNotifications ?? 0;

        if (currentUser?.role !== "admin") {
            $("statOneLabel").textContent = "My Bookings";
            $("statTwoLabel").textContent = "Today's Bookings";
            $("statThreeLabel").textContent = "Vehicle Detections";
            $("statFourLabel").textContent = "My Notifications";
        }

    } catch (error) {
        console.error("Dashboard error:", error);
    }
}



async function loadAdvisorsForBooking() {
    if (currentUser?.role !== "admin") return;

    const select = $("bookingAdvisor");

    if (!select) return;

    try {
        const response = await api("/api/advisors");

        const advisors = Array.isArray(response)
            ? response
            : response.advisors || [];

        select.innerHTML =
            '<option value="">Select service advisor</option>';

        const activeAdvisors = advisors.filter(
            (advisor) => advisor.is_active !== false
        );

        activeAdvisors.forEach((advisor) => {
            const option = document.createElement("option");

            option.value = advisor.id;
            option.textContent =
                `${advisor.name} (${advisor.username})`;

            select.appendChild(option);
        });

        if (!activeAdvisors.length) {
            select.innerHTML =
                '<option value="">No active advisors available</option>';
        }

    } catch (error) {
        console.error("Advisor dropdown error:", error);

        select.innerHTML =
            '<option value="">Could not load advisors</option>';
    }
}



$("bookingForm")?.addEventListener("submit", async (event) => {
    event.preventDefault();

    if (currentUser?.role !== "admin") {
        showMessage("bookingMessage", "Only administrators can register bookings.", "error");
        return;
    }

    hideMessage("bookingMessage");

    const form = event.currentTarget;
    const formData = new FormData(form);

    const advisorId = Number(formData.get("advisor_id"));

    if (!advisorId) {
        showMessage(
            "bookingMessage",
            "Please select a service advisor before saving.",
            "error"
        );
        return;
    }

    const payload = {
        customer_name: formData.get("customer_name").trim(),
        phone: formData.get("phone").trim(),
        vehicle_number: formData.get("vehicle_number").trim().toUpperCase(),
        vehicle_model: formData.get("vehicle_model").trim(),
        booking_date: formData.get("booking_date"),
        booking_time: formData.get("booking_time"),
        service_type: formData.get("service_type"),
        status: formData.get("status"),
        advisor_id: advisorId
    };

    const submitButton = form.querySelector('[type="submit"]');
    submitButton.disabled = true;
    submitButton.textContent = "Saving...";

    try {
        const result = await api("/api/bookings", {
            method: "POST",
            body: JSON.stringify(payload)
        });

        showMessage(
            "bookingMessage",
            result.message || "Booking registered successfully."
        );

        form.reset();

        const dateInput = form.querySelector('[name="booking_date"]');

        if (dateInput) {
            const today = new Date();
            dateInput.value = [
                today.getFullYear(),
                String(today.getMonth() + 1).padStart(2, "0"),
                String(today.getDate()).padStart(2, "0")
            ].join("-");
        }

        await loadBookings();
        await loadDashboard();
        await loadAdvisorsForBooking();

    } catch (error) {
        showMessage("bookingMessage", error.message, "error");

    } finally {
        submitButton.disabled = false;
        submitButton.textContent = "Save Booking";
    }
});

$("bookingImportForm")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    if (currentUser?.role !== "admin") {
        showMessage("bookingImportMessage", "Only administrators can import bookings.", "error");
        return;
    }

    const file = $("bookingCsvFile").files[0];
    if (!file) {
        showMessage("bookingImportMessage", "Choose a CSV file first.", "error");
        return;
    }

    hideMessage("bookingImportMessage");
    const button = $("bookingImportSubmit");
    const payload = new FormData();
    payload.append("file", file);
    button.disabled = true;
    button.textContent = "Importing...";

    try {
        const result = await api("/api/bookings/import", {
            method: "POST",
            body: payload
        });
        showMessage("bookingImportMessage", result.message || "CSV imported.");
        form.reset();
        await loadBookings();
        await loadDashboard();
    } catch (error) {
        showMessage("bookingImportMessage", error.message, "error");
    } finally {
        button.disabled = false;
        button.textContent = "Import CSV";
    }
});


async function loadBookings() {
    try {
        const response = await api("/api/bookings");

        const bookings = Array.isArray(response)
            ? response
            : response.bookings || [];

        renderBookings(bookings);

        renderRecentBookings(bookings);

    } catch (error) {
        console.error("Booking list error:", error);

        $("bookingRows").innerHTML =
            `<tr><td colspan="10" class="empty-cell">${escapeHtml(error.message)}</td></tr>`;
    }
}

function renderBookings(bookings) {
    const tbody = $("bookingRows");

    if (!tbody) return;

    if (!bookings.length) {
        tbody.innerHTML =
            '<tr><td colspan="10" class="empty-cell">No bookings found.</td></tr>';
        return;
    }

    tbody.innerHTML = bookings.map((booking) => `
        <tr>
            <td>${escapeHtml(booking.customer_name)}</td>
            <td>${escapeHtml(booking.phone)}</td>
            <td><strong>${escapeHtml(booking.vehicle_number)}</strong></td>
            <td>${escapeHtml(booking.vehicle_model)}</td>
            <td>${escapeHtml(formatDate(booking.booking_date))}</td>
            <td>${escapeHtml(formatTime(booking.booking_time))}</td>
            <td>${escapeHtml(booking.service_type)}</td>
            <td>${escapeHtml(booking.advisor || booking.advisor_name || "—")}</td>
            <td>
                <span class="status-pill ${statusClass(booking.status)}">
                    ${escapeHtml(booking.status)}
                </span>
            </td>
            <td>
                <button class="table-action"
                    data-booking-id="${Number(booking.id)}">
                    View
                </button>
            </td>
        </tr>
    `).join("");

    tbody.querySelectorAll("[data-booking-id]").forEach((button) => {
        button.addEventListener("click", () => {
            viewBooking(Number(button.dataset.bookingId));
        });
    });
}

function renderRecentBookings(bookings) {
    const tbody = $("recentBookingRows");

    if (!tbody) return;

    const recent = [...bookings].slice(0, 5);

    if (!recent.length) {
        tbody.innerHTML =
            '<tr><td colspan="4" class="empty-cell">No bookings yet.</td></tr>';
        return;
    }

    tbody.innerHTML = recent.map((booking) => `
        <tr>
            <td>${escapeHtml(booking.customer_name)}</td>
            <td>${escapeHtml(booking.vehicle_number)}</td>
            <td>${escapeHtml(formatDate(booking.booking_date))}</td>
            <td>
                <span class="status-pill ${statusClass(booking.status)}">
                    ${escapeHtml(booking.status)}
                </span>
            </td>
        </tr>
    `).join("");
}



async function viewBooking(bookingId) {
    try {
        const booking = await api(`/api/bookings/${bookingId}`);

        const details = [
            ["Customer", booking.customer_name],
            ["Phone", booking.phone],
            ["Vehicle Number", booking.vehicle_number],
            ["Vehicle Model", booking.vehicle_model],
            ["Booking Date", formatDate(booking.booking_date)],
            ["Booking Time", formatTime(booking.booking_time)],
            ["Service Type", booking.service_type],
            ["Advisor", booking.advisor || booking.advisor_name || "—"],
            ["Status", booking.status]
        ];

        $("bookingDetailsContent").innerHTML = details.map(([label, value]) => `
            <div class="detail-row">
                <span>${escapeHtml(label)}</span>
                <strong>${escapeHtml(value ?? "—")}</strong>
            </div>
        `).join("");

        $("bookingDialog").showModal();

    } catch (error) {
        alert(`Could not load booking: ${error.message}`);
    }
}

$("closeBookingDialog")?.addEventListener("click", () => {
    $("bookingDialog").close();
});



$("videoFile")?.addEventListener("change", (event) => {
    const file = event.target.files[0];

    $("selectedVideoName").textContent =
        file ? `${file.name} · ${(file.size / (1024 * 1024)).toFixed(2)} MB`
             : "No video selected";
});

$("videoForm")?.addEventListener("submit", async (event) => {
    event.preventDefault();

    if (currentUser?.role !== "admin") return;

    const file = $("videoFile").files[0];

    if (!file) {
        showMessage("videoMessage", "Please select a video file.", "error");
        return;
    }

    const formData = new FormData();

    // This must match the FastAPI parameter: video: UploadFile = File(...)
    formData.append("video", file);

    const button = $("videoSubmit");

    button.disabled = true;
    button.textContent = "Processing video...";

    $("videoProgress").hidden = false;
    hideMessage("videoMessage");

    $("videoResults").innerHTML =
        '<tr><td colspan="9" class="empty-cell">Processing video. Results will show only high-confidence recognized plates.</td></tr>';

    try {
        const result = await api("/api/video/upload", {
            method: "POST",
            body: formData
        });

        renderVideoResults(result);

        showMessage(
            "videoMessage",
            result.message || "Video processing completed successfully."
        );

        await loadDashboard();
        await loadNotifications();

    } catch (error) {
        console.error("Video processing error:", error);

        showMessage("videoMessage", error.message, "error");

        $("videoResults").innerHTML =
            `<tr><td colspan="9" class="empty-cell">${escapeHtml(error.message)}</td></tr>`;

    } finally {
        button.disabled = false;
        button.textContent = "Process Video";
        $("videoProgress").hidden = true;
    }
});

function renderVideoResults(result) {
    const results = result.results || [];

    $("videoSummary").textContent =
        `Recognized plates: ${results.length} · ` +
        `Matched: ${result.matched_count ?? 0} · ` +
        `Unmatched: ${result.unmatched_count ?? 0} · ` +
        `Walk-ins assigned: ${result.walk_in_assigned_count ?? 0} · ` +
        `Speed: ${Number.isFinite(Number(result.processing_fps)) ? Number(result.processing_fps).toFixed(2) : "—"} fps (target ${Number(result.target_sample_fps ?? 4).toFixed(0)}) · ` +
        `New notifications: ${result.notifications_created ?? 0} · ` +
        `Skipped notifications: ${result.notifications_skipped ?? 0}`;

    if (!results.length) {
        $("videoResults").innerHTML =
            '<tr><td colspan="9" class="empty-cell">No high-confidence number plates were recognized in this video.</td></tr>';
        return;
    }

    $("videoResults").innerHTML = results.map((item) => {
        const imageUrl = safeLocalUploadUrl(item.image_path);

        return `
            <tr>
                <td><strong>${escapeHtml(item.plate_display || item.plate_number || "Not extracted")}</strong></td>
                <td>
                    <span class="status-pill ${statusClass(item.status)}">
                        ${escapeHtml(item.status || "Not matched")}
                    </span>
                </td>
                <td>${escapeHtml(item.customer_name || "—")}</td>
                <td>${escapeHtml(item.booking_time ? formatTime(item.booking_time) : "—")}</td>
                <td>${escapeHtml(item.advisor || "—")}</td>
                <td>${formatConfidence(item.confidence)}</td>
                <td>${formatConfidence(item.ocr_confidence)}</td>
                <td>${escapeHtml(item.frame_number ?? "—")}</td>
                <td>
                    ${imageUrl
                        ? `<a href="${escapeHtml(imageUrl)}" target="_blank" rel="noopener"><img class="video-result-thumb" src="${escapeHtml(imageUrl)}" alt="Best frame for ${escapeHtml(item.plate_display || item.plate_number)}"></a>`
                        : "—"}
                </td>
            </tr>
        `;
    }).join("");
}

function safeLocalUploadUrl(path) {
    if (!path) return null;

    // Accept only application-local upload/static paths.
    const value = String(path);

    if (value.startsWith("/uploads/") || value.startsWith("/static/")) {
        return value;
    }

    return null;
}

function formatConfidence(value) {
    if (value === null || value === undefined || value === "") return "—";

    const number = Number(value);

    if (!Number.isFinite(number)) return "—";

    return `${(number <= 1 ? number * 100 : number).toFixed(1)}%`;
}



$("startMonitor")?.addEventListener("click", async () => {
    try {
        const result = await api("/api/monitor/start", {
            method: "POST"
        });

        showMonitorMessage(
            result.message || "Monitoring start requested.",
            "success"
        );

        await loadMonitorStatus();

    } catch (error) {
        showMonitorMessage(error.message, "error");
    }
});

$("stopMonitor")?.addEventListener("click", async () => {
    try {
        const result = await api("/api/monitor/stop", {
            method: "POST"
        });

        showMonitorMessage(
            result.message || "Monitoring stop requested.",
            "info"
        );

        await loadMonitorStatus();

    } catch (error) {
        showMonitorMessage(error.message, "error");
    }
});

function showMonitorMessage(message, type = "info") {
    const element = $("monitorError");

    element.textContent = message;
    element.className = `message ${type}`;
    element.hidden = false;
}

async function loadMonitorStatus() {
    if (currentUser?.role !== "admin") return;

    try {
        const data = await api("/api/monitor/status");

        $("monitorStatusText").textContent =
            data.running ? "Monitoring active" : "Monitor stopped";

        $("monitorStatusDot").style.background =
            data.running ? "#16865b" : "#c44e4e";

        $("monitorFrames").textContent =
            `${data.frames_processed ?? 0} frames processed`;

        if (data.last_error) {
            showMonitorMessage(data.last_error, "error");
        } else {
            $("monitorError").hidden = true;
        }

        // Display the latest annotated frame from the backend.
        if (data.latest_frame_url) {
            const image = $("liveFrame");

            const separator = data.latest_frame_url.includes("?") ? "&" : "?";

            image.src =
                `${data.latest_frame_url}${separator}t=${Date.now()}`;

            image.hidden = false;
            $("cameraPlaceholder").hidden = true;

        } else {
            $("liveFrame").hidden = true;
            $("cameraPlaceholder").hidden = false;
        }

        if (data.last_result) {
            renderLiveRecognition(data.last_result);
        }

    } catch (error) {
        console.error("Monitor status error:", error);
        $("monitorStatusText").textContent = "Status unavailable";
    }
}

function renderLiveRecognition(data) {
    const status = String(data.status || "Waiting");
    const showPlate = ["matched", "unmatched", "walk_in_assigned", "duplicate"].includes(status);

    $("liveDetectionStatus").textContent = status;
    $("liveDetectionStatus").className =
        `status-pill ${statusClass(status)}`;

    $("livePlate").textContent =
        showPlate ? (data.plate_display || data.plate_number || "Not detected") : "Waiting for a high-confidence plate";

    $("liveOCR").textContent =
        showPlate ? `OCR text: ${data.ocr_text || "No text extracted"}` : "OCR text hidden until confidence is high";

    $("liveConfidence").textContent =
        formatConfidence(data.confidence);

    $("liveOcrConfidence").textContent =
        formatConfidence(data.ocr_confidence);

    $("liveCustomer").textContent =
        data.customer_name || "No booking match";

    $("liveAppointment").textContent =
        data.booking_time ? formatTime(data.booking_time) : "—";

    $("liveVehicle").textContent =
        data.vehicle_model || "—";

    $("liveAdvisor").textContent =
        data.advisor || "—";

    $("liveService").textContent =
        data.service_type || "—";

    $("liveRecognitionMessage").textContent =
        data.message || "Detection result received.";
}



$("advisorForm")?.addEventListener("submit", async (event) => {
    event.preventDefault();

    if (currentUser?.role !== "admin") return;

    const form = event.currentTarget;
    const formData = new FormData(form);

    const payload = {
        name: formData.get("name").trim(),
        username: formData.get("username").trim(),
        password: formData.get("password"),
        phone: formData.get("phone").trim(),
        email: formData.get("email").trim() || null
    };

    const button = form.querySelector('[type="submit"]');

    button.disabled = true;
    button.textContent = "Creating...";

    try {
        const result = await api("/api/advisors", {
            method: "POST",
            body: JSON.stringify(payload)
        });

        showMessage(
            "advisorMessage",
            result.message || "Advisor account created successfully."
        );

        form.reset();

        await loadAdvisors();
        await loadAdvisorsForBooking();

    } catch (error) {
        showMessage("advisorMessage", error.message, "error");

    } finally {
        button.disabled = false;
        button.textContent = "Create Advisor";
    }
});

async function loadAdvisors() {
    if (currentUser?.role !== "admin") return;

    try {
        const response = await api("/api/advisors");

        const advisors = Array.isArray(response)
            ? response
            : response.advisors || [];

        if (!advisors.length) {
            $("advisorList").textContent = "No advisors registered.";
            return;
        }

        $("advisorList").innerHTML = advisors.map((advisor) => `
            <div class="advisor-item">
                <strong>${escapeHtml(advisor.name)}</strong>
                <small>Username: ${escapeHtml(advisor.username)}</small>
                <label>WhatsApp phone
                    <input id="advisorPhone-${Number(advisor.id)}" type="tel" value="${escapeHtml(advisor.phone || "")}" placeholder="7025150147">
                </label>
                <label>Notification email
                    <input id="advisorEmail-${Number(advisor.id)}" type="email" value="${escapeHtml(advisor.email || "")}" placeholder="advisor@example.com">
                </label>
                <button class="table-action" type="button" data-save-advisor="${Number(advisor.id)}">Save notification contacts</button>
                <div id="advisorContactMessage-${Number(advisor.id)}" class="message" hidden></div>
                <small>Status: ${advisor.is_active === false ? "Inactive" : "Active"}</small>
            </div>
        `).join("");

        document.querySelectorAll("[data-save-advisor]").forEach((button) => {
            button.addEventListener("click", async () => {
                const advisorId = Number(button.dataset.saveAdvisor);
                button.disabled = true;
                try {
                    const result = await api(`/api/advisors/${advisorId}/contact`, {
                        method: "PATCH",
                        body: JSON.stringify({
                            phone: $(`advisorPhone-${advisorId}`).value.trim(),
                            email: $(`advisorEmail-${advisorId}`).value.trim() || null
                        })
                    });
                    showMessage(`advisorContactMessage-${advisorId}`, result.message);
                } catch (error) {
                    showMessage(`advisorContactMessage-${advisorId}`, error.message, "error");
                } finally {
                    button.disabled = false;
                }
            });
        });

    } catch (error) {
        $("advisorList").textContent = error.message;
    }
}



async function loadNotifications() {
    try {
        if (currentUser?.role === "admin") {
            await loadNotificationSetupStatus();
        }
        const endpoint =
            currentUser?.role === "admin"
                ? "/api/admin/notifications"
                : "/api/advisor/notifications";

        const response = await api(endpoint);

        const notifications = Array.isArray(response)
            ? response
            : response.notifications || [];

        renderNotifications(notifications);

    } catch (error) {
        console.error("Notification error:", error);

        $("notificationList").textContent =
            `Could not load notifications: ${error.message}`;
    }
}

async function loadNotificationSetupStatus() {
    const panel = $("notificationSetupStatus");
    if (!panel) return;
    try {
        const data = await api("/api/admin/notification-status");
        const renderChannel = (name, status) => `
            <div class="notification-setup-channel">
                <strong>${escapeHtml(name)}: ${status.ready ? "Ready" : "Not configured"}</strong>
                <ul>${(status.messages || []).map((message) => `<li>${escapeHtml(message)}</li>`).join("")}</ul>
            </div>`;
        panel.innerHTML = `<h3>External alert setup</h3>${renderChannel("Gmail", data.email)}${data.email.test_ready ? '<button id="testGmailButton" class="secondary-btn" type="button">Send test email to sender account</button>' : ''}<div id="testGmailMessage" class="message" hidden></div>${renderChannel("WhatsApp", data.whatsapp)}`;
        $("testGmailButton")?.addEventListener("click", async (event) => {
            const button = event.currentTarget;
            button.disabled = true;
            try {
                const result = await api("/api/admin/notifications/test-email", { method: "POST" });
                showMessage("testGmailMessage", result.message);
            } catch (error) {
                showMessage("testGmailMessage", error.message, "error");
            } finally {
                button.disabled = false;
            }
        });
    } catch (error) {
        panel.textContent = `Could not check notification setup: ${error.message}`;
    }
}

function renderNotifications(notifications) {
    const container = $("notificationList");

    if (!notifications.length) {
        container.innerHTML =
            '<div class="empty-cell">No notifications available.</div>';
        return;
    }

    container.innerHTML = notifications.map((notification) => {
        const completed = String(notification.status || "").toLowerCase() === "completed";
        const state = `${completed ? "Completed" : "Open"} · ${notification.is_read ? "Read" : "Unread"}`;
        return `
        <div class="notification-item ${notification.is_read ? "" : "unread"} ${completed ? "completed" : ""}">
            <div>
                <strong>${escapeHtml(notification.title || "Vehicle Notification")}</strong>
                <p>${escapeHtml(notification.message)}</p>
                <small>
                    ${notification.advisor ? `${escapeHtml(notification.advisor)} · ` : ""}
                    ${escapeHtml(notification.channel || "System")}
                    · ${escapeHtml(notification.created_at || "")} · ${state}
                </small>
            </div>
            <div class="notification-actions">
                <button class="table-action" data-notification-id="${Number(notification.id)}" data-next-read="${!notification.is_read}">
                    Mark ${notification.is_read ? "unread" : "read"}
                </button>
                <button class="table-action" data-notification-id="${Number(notification.id)}" data-next-status="${completed ? "created" : "completed"}">
                    ${completed ? "Reopen" : "Mark completed"}
                </button>
            </div>
        </div>
    `;
    }).join("");

    container.querySelectorAll("[data-next-read]").forEach((button) => {
        button.addEventListener("click", async () => {
            await updateNotification(Number(button.dataset.notificationId), {
                is_read: button.dataset.nextRead === "true"
            });
        });
    });
    container.querySelectorAll("[data-next-status]").forEach((button) => {
        button.addEventListener("click", async () => {
            await updateNotification(Number(button.dataset.notificationId), {
                status: button.dataset.nextStatus
            });
        });
    });
}

async function updateNotification(notificationId, changes) {
    try {
        await api(`/api/notifications/${notificationId}`, {
            method: "PATCH",
            body: JSON.stringify(changes)
        });

        await loadNotifications();
        await loadDashboard();

    } catch (error) {
        alert(`Could not mark notification as read: ${error.message}`);
    }
}



$("refreshBookings")?.addEventListener("click", loadBookings);

$("refreshNotifications")?.addEventListener("click", loadNotifications);

function startBackgroundRefresh() {
    if (notificationTimer) clearInterval(notificationTimer);

    notificationTimer = setInterval(async () => {
        await loadDashboard();

        if (currentSection === "notifications") {
            await loadNotifications();
        }

        if (currentSection === "bookings") {
            await loadBookings();
        }

        if (currentUser?.role === "admin" && currentSection === "monitor") {
            await loadMonitorStatus();
        }

    }, 5000);
}



$("logoutBtn")?.addEventListener("click", async () => {
    try {
        await api("/api/logout", {
            method: "POST"
        });
    } catch (error) {
        console.error("Logout error:", error);
    }

    window.location.href = "/";
});



document.addEventListener("DOMContentLoaded", initializeApp);
