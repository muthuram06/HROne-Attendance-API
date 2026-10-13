
const $ = (selector) => document.querySelector(selector);

let employees = [];
let attendanceByEmployee = new Map();
let allAttendanceRecords = [];
let toastTimer;

const pageConfig = {
  overview: {
    eyebrow: "WORKSPACE / OVERVIEW",
    title: "Attendance overview",
    description: "Manage your team and daily attendance."
  },
  employees: {
    eyebrow: "WORKSPACE / EMPLOYEES",
    title: "Employee directory",
    description: "Manage employee profiles and daily check-in/check-out."
  },
  attendance: {
    eyebrow: "WORKSPACE / ATTENDANCE",
    title: "Attendance register",
    description: "View recorded attendance, working hours, and status."
  }
};

function todayInIndia() {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Kolkata",
    year: "numeric",
    month: "2-digit",
    day: "2-digit"
  }).formatToParts(new Date());

  const part = (type) => parts.find((item) => item.type === type).value;

  return `${part("year")}-${part("month")}-${part("day")}`;
}

function formatDate(dateString) {
  if (!dateString) return "—";

  const date = new Date(`${dateString}T12:00:00+05:30`);

  if (Number.isNaN(date.getTime())) return dateString;

  return new Intl.DateTimeFormat("en-IN", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    timeZone: "Asia/Kolkata"
  }).format(date);
}

function formatTime(value) {
  if (!value) return "—";

  const date = new Date(value);

  if (Number.isNaN(date.getTime())) return "—";

  return new Intl.DateTimeFormat("en-IN", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: true,
    timeZone: "Asia/Kolkata"
  }).format(date);
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;"
  })[char]);
}

async function api(url, options = {}) {
  const response = await fetch(url, {
    ...options,
    headers: {
      ...(options.body ? { "Content-Type": "application/json" } : {}),
      ...options.headers
    }
  });

  const data = await response.json().catch(() => ({}));

  if (!response.ok) {
    const detail = data.detail;
    const message = Array.isArray(detail)
      ? detail.map((item) => item.msg).join(", ")
      : detail || `Request failed (${response.status})`;

    throw new Error(message);
  }

  return data;
}

function normalizeArray(data, keys = []) {
  if (Array.isArray(data)) return data;

  for (const key of keys) {
    if (Array.isArray(data?.[key])) return data[key];
  }

  return [];
}

function setConnection(online, text) {
  $(".connection-dot")?.classList.toggle("online", online);
  $(".connection-dot")?.classList.toggle("offline", !online);

  const status = $("#connection-status");
  if (status) status.textContent = text;
}

function showToast(message) {
  const toast = $("#toast");
  if (!toast) return;

  toast.textContent = message;
  toast.classList.add("show");

  clearTimeout(toastTimer);

  toastTimer = setTimeout(() => {
    toast.classList.remove("show");
  }, 3000);
}

function todayRecord(employeeId) {
  return (attendanceByEmployee.get(employeeId) || []).find(
    (record) => record.attendance_date === todayInIndia()
  );
}

function attendanceStatus(record) {
  if (record.check_in && record.check_out) {
    return { label: "Completed", className: "completed" };
  }

  if (record.check_in) {
    return { label: "In progress", className: "in-progress" };
  }

  return { label: "Not marked", className: "not-marked" };
}

function updateStats() {
  let checkedIn = 0;
  let pending = 0;
  let completed = 0;

  for (const employee of employees) {
    const record = todayRecord(employee.employee_id);

    if (!record) continue;

    checkedIn++;

    if (record.check_out) {
      completed++;
    } else if (record.check_in) {
      pending++;
    }
  }

  $("#total-employees").textContent = employees.length;
  $("#checked-in").textContent = checkedIn;
  $("#pending-checkout").textContent = pending;
  $("#completed").textContent = completed;

  $("#employee-count").textContent =
    `${employees.length} employee${employees.length === 1 ? "" : "s"}`;

  $("#overview-employee-count").textContent =
    `${employees.length} employee${employees.length === 1 ? "" : "s"}`;
}

function renderEmployees() {
  const query = $("#search-input").value.trim().toLowerCase();

  const filtered = employees.filter((employee) => [
    employee.employee_id,
    employee.name,
    employee.department,
    employee.designation,
    employee.email
  ].some((value) => String(value || "").toLowerCase().includes(query)));

  const tbody = $("#employee-table");

  if (!filtered.length) {
    tbody.innerHTML = `
      <tr>
        <td colspan="5" class="empty">
          ${employees.length
            ? "No employees match your search."
            : "No employees registered yet. Add your first employee."}
        </td>
      </tr>`;

    $("#table-footer").textContent = "No matching records";
    return;
  }

  tbody.innerHTML = filtered.map((employee) => {
    const record = todayRecord(employee.employee_id);
    const statusInfo = record
      ? attendanceStatus(record)
      : { label: "Not marked", className: "not-marked" };

    let actionLabel = "Check in";
    let action = "check-in";
    let disabled = "";

    if (record && !record.check_out) {
      actionLabel = "Check out";
      action = "check-out";
    } else if (record && record.check_out) {
      actionLabel = "Completed";
      action = "completed";
      disabled = "disabled";
    }

    return `
      <tr>
        <td>
          <div class="employee-name">${escapeHtml(employee.name)}</div>
          <div class="employee-id">${escapeHtml(employee.employee_id)}</div>
        </td>
        <td>${escapeHtml(employee.department)}</td>
        <td>${record ? escapeHtml(formatTime(record.check_in)) : "—"}</td>
        <td>
          <span class="status ${statusInfo.className}">
            ${statusInfo.label}
          </span>
        </td>
        <td>
          <button class="action-button"
            data-action="${action}"
            data-id="${escapeHtml(employee.employee_id)}"
            ${disabled}>
            ${actionLabel}
          </button>
        </td>
      </tr>`;
  }).join("");

  $("#table-footer").textContent =
    `Showing ${filtered.length} of ${employees.length} employees`;
}

function buildAttendanceRecords() {
  const employeeMap = new Map(
    employees.map((employee) => [employee.employee_id, employee])
  );

  allAttendanceRecords = [];

  for (const [employeeId, records] of attendanceByEmployee.entries()) {
    const employee = employeeMap.get(employeeId);

    for (const record of records) {
      allAttendanceRecords.push({
        ...record,
        employee_id: record.employee_id || employeeId,
        employee_name: employee?.name || employeeId
      });
    }
  }

  allAttendanceRecords.sort((a, b) => {
    const dateComparison = String(b.attendance_date || "")
      .localeCompare(String(a.attendance_date || ""));

    if (dateComparison !== 0) return dateComparison;

    return String(b.check_in || "").localeCompare(String(a.check_in || ""));
  });
}

function renderOverviewAttendance() {
  const container = $("#overview-attendance");

  const todayRecords = allAttendanceRecords.filter(
    (record) => record.attendance_date === todayInIndia()
  );

  if (!todayRecords.length) {
    container.innerHTML = `
      <div class="empty">
        No attendance recorded today.
        <br>Check in an employee from the Employees page.
      </div>`;
    return;
  }

  container.innerHTML = todayRecords.slice(0, 6).map((record) => {
    const status = attendanceStatus(record);

    return `
      <div class="overview-record">
        <div class="overview-record-name">
          ${escapeHtml(record.employee_name)}
          <small>${escapeHtml(record.employee_id)}</small>
          <div class="overview-record-time">
            Check-in: ${escapeHtml(formatTime(record.check_in))}
            ${record.check_out
              ? ` · Check-out: ${escapeHtml(formatTime(record.check_out))}`
              : ""}
          </div>
        </div>
        <span class="status ${status.className}">
          ${status.label}
        </span>
      </div>`;
  }).join("");
}

function renderAttendanceRegister() {
  const query = $("#attendance-search").value.trim().toLowerCase();
  const selectedDate = $("#attendance-date").value;

  const filtered = allAttendanceRecords.filter((record) => {
    const searchText =
      `${record.employee_name} ${record.employee_id}`.toLowerCase();

    const matchesSearch = searchText.includes(query);
    const matchesDate =
      !selectedDate || record.attendance_date === selectedDate;

    return matchesSearch && matchesDate;
  });

  let inProgress = 0;
  let completed = 0;

  for (const record of filtered) {
    if (record.check_in && record.check_out) {
      completed++;
    } else if (record.check_in) {
      inProgress++;
    }
  }

  $("#attendance-total").textContent = filtered.length;
  $("#attendance-in-progress").textContent = inProgress;
  $("#attendance-completed").textContent = completed;

  const tbody = $("#attendance-table");

  if (!filtered.length) {
    tbody.innerHTML = `
      <tr>
        <td colspan="6" class="empty">
          No attendance records found for the selected filters.
        </td>
      </tr>`;

    $("#attendance-footer").textContent = "No matching attendance records";
    return;
  }

  tbody.innerHTML = filtered.map((record) => {
    const status = attendanceStatus(record);

    const hours = record.working_hours == null
      ? (record.check_in ? "In progress" : "—")
      : `${Number(record.working_hours).toFixed(2)} hrs`;

    return `
      <tr>
        <td>
          <div class="attendance-employee">
            ${escapeHtml(record.employee_name)}
            <small>${escapeHtml(record.employee_id)}</small>
          </div>
        </td>
        <td>${escapeHtml(formatDate(record.attendance_date))}</td>
        <td>${escapeHtml(formatTime(record.check_in))}</td>
        <td>${escapeHtml(formatTime(record.check_out))}</td>
        <td>${escapeHtml(hours)}</td>
        <td>
          <span class="attendance-status ${status.className}">
            ${status.label}
          </span>
        </td>
      </tr>`;
  }).join("");

  $("#attendance-footer").textContent =
    `Showing ${filtered.length} of ${allAttendanceRecords.length} attendance records`;
}

function renderAllViews() {
  updateStats();
  renderEmployees();
  buildAttendanceRecords();
  renderOverviewAttendance();
  renderAttendanceRegister();
}

async function loadDashboard() {
  $("#today-date").textContent = formatDate(todayInIndia());

  $("#employee-table").innerHTML = `
    <tr><td colspan="5" class="empty">Loading employees...</td></tr>`;

  $("#attendance-table").innerHTML = `
    <tr><td colspan="6" class="empty">Loading attendance records...</td></tr>`;

  try {
    const employeeData = await api("/employees");
    employees = normalizeArray(employeeData, ["employees"]);

    const results = await Promise.all(
      employees.map(async (employee) => {
        try {
          const response = await api(
            `/attendance/${encodeURIComponent(employee.employee_id)}`
          );

          const records = normalizeArray(response, ["records", "attendance"]);

          return [employee.employee_id, records];
        } catch (error) {
          console.error(
            `Could not load attendance for ${employee.employee_id}:`,
            error
          );

          return [employee.employee_id, []];
        }
      })
    );

    attendanceByEmployee = new Map(results);

    setConnection(true, "Connected");
    renderAllViews();
  } catch (error) {
    console.error("Dashboard loading failed:", error);
    setConnection(false, "Connection failed");

    $("#employee-table").innerHTML = `
      <tr>
        <td colspan="5" class="empty">
          Could not load employees.
          <br>${escapeHtml(error.message)}
        </td>
      </tr>`;

    $("#table-footer").textContent = "Unable to load records";

    $("#attendance-table").innerHTML = `
      <tr>
        <td colspan="6" class="empty">
          Attendance data is unavailable because employees could not be loaded.
        </td>
      </tr>`;

    $("#attendance-footer").textContent = "Unable to load records";
    $("#overview-attendance").innerHTML =
      '<div class="empty">Unable to load today’s attendance.</div>';

    showToast("Could not load dashboard data.");
  }
}

function navigateTo(viewName) {
  if (!pageConfig[viewName]) viewName = "overview";

  document.querySelectorAll(".page-view").forEach((section) => {
    section.hidden = section.id !== `${viewName}-view`;
  });

  document.querySelectorAll(".nav-link[data-view]").forEach((link) => {
    link.classList.toggle("active", link.dataset.view === viewName);
  });

  $("#page-eyebrow").textContent = pageConfig[viewName].eyebrow;
  $("#page-title").textContent = pageConfig[viewName].title;
  $("#page-description").textContent = pageConfig[viewName].description;

  history.replaceState(null, "", `#${viewName}`);

  if (viewName === "attendance") {
    renderAttendanceRegister();
  }

  if (viewName === "employees") {
    renderEmployees();
  }

  window.scrollTo({ top: 0, behavior: "auto" });
}

// Navigation: Overview, Employees, Attendance
document.querySelectorAll("[data-view]").forEach((element) => {
  element.addEventListener("click", (event) => {
    event.preventDefault();
    navigateTo(element.dataset.view);
  });
});

// Create employee
$("#employee-form").addEventListener("submit", async (event) => {
  event.preventDefault();

  const button = $("#create-btn");
  const message = $("#form-message");

  const employee = Object.fromEntries(
    new FormData(event.currentTarget).entries()
  );

  button.disabled = true;
  button.textContent = "Creating...";
  message.textContent = "";
  message.className = "form-message";

  try {
    await api("/employees", {
      method: "POST",
      body: JSON.stringify(employee)
    });

    event.currentTarget.reset();

    message.textContent = "Employee created successfully.";
    message.classList.add("success");

    await loadDashboard();
    showToast("Employee created successfully.");
  } catch (error) {
    message.textContent = error.message;
    message.classList.add("error");
  } finally {
    button.disabled = false;
    button.textContent = "Create employee";
  }
});

// Check in / check out from the employee directory
$("#employee-table").addEventListener("click", async (event) => {
  const button = event.target.closest("button[data-action]");

  if (!button || button.disabled) return;

  const employeeId = button.dataset.id;
  const action = button.dataset.action;

  if (!["check-in", "check-out"].includes(action)) return;

  button.disabled = true;
  button.textContent = "Saving...";

  try {
    await api(`/attendance/${action}`, {
      method: "POST",
      body: JSON.stringify({ employee_id: employeeId })
    });

    showToast(
      action === "check-in"
        ? "Attendance marked successfully."
        : "Check-out recorded successfully."
    );

    await loadDashboard();
  } catch (error) {
    showToast(error.message);
    await loadDashboard();
  }
});

// Search employees
$("#search-input").addEventListener("input", renderEmployees);

// Refresh the full dashboard and its attendance records
$("#refresh-btn").addEventListener("click", loadDashboard);
$("#attendance-refresh").addEventListener("click", loadDashboard);

// Open the add-employee form
$("#new-employee-btn").addEventListener("click", () => {
  $("#add-panel").scrollIntoView({
    behavior: "smooth",
    block: "start"
  });

  $("#employee_id").focus({ preventScroll: true });
});

// Search and filter attendance
$("#attendance-search").addEventListener(
  "input",
  renderAttendanceRegister
);

$("#attendance-date").addEventListener(
  "change",
  renderAttendanceRegister
);

$("#clear-attendance-filters").addEventListener("click", () => {
  $("#attendance-search").value = "";
  $("#attendance-date").value = "";
  renderAttendanceRegister();
});

// Start the dashboard
loadDashboard();

const initialView = window.location.hash.replace("#", "");

navigateTo(pageConfig[initialView] ? initialView : "overview");
