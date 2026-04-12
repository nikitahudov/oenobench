/* OenoBench Dashboard — Client-side polling */

const REFRESH_INTERVAL = 30000;

async function fetchJSON(url) {
    const resp = await fetch(url);
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    return resp.json();
}

function formatNumber(n) {
    return n != null ? n.toLocaleString() : "\u2014";
}

function progressClass(pct) {
    if (pct < 33) return "low";
    if (pct < 66) return "mid";
    return "high";
}

function formatDomain(name) {
    return name.replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase());
}

function formatSourceType(name) {
    const map = {
        "encyclopedia": "Encyclopedia (Wikipedia)",
        "knowledge_base": "Knowledge Base (Wikidata)",
        "dataset": "Datasets (HuggingFace/Kaggle)",
        "government_extension": "Gov. Extension",
        "government_registry": "Gov. Registry (INAO)",
        "government_data": "Gov. Data (UC Davis)",
        "academic_journal": "Academic Journals",
        "consortium": "Wine Consortiums",
        "national_wine_body": "National Wine Bodies",
        "government": "Government (TTB)",
        "academic_database": "Academic Database",
        "official_body": "Official Wine Bodies",
        "international_organisation": "Intl. Organisations",
        "reference": "Reference",
        "trade_body": "Trade Bodies",
    };
    return map[name] || name.replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase());
}

function escapeHtml(str) {
    const div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
}

/* ── Project Overview ───────────────────────────────────────────────────── */

function updateProject(data) {
    // Timeline bar
    const timeline = document.getElementById("timeline");
    timeline.innerHTML = "";
    for (const phase of data.phases) {
        const cls = phase.status === "complete" ? "complete" :
                    phase.status === "in_progress" ? "in_progress" : "not_started";
        const actual = phase.actual ? ` (${phase.actual})` : "";
        timeline.innerHTML += `
            <div class="timeline-phase ${cls}">
                <span class="phase-num">${phase.id}</span>
                <span class="phase-label">${escapeHtml(phase.name)}${actual}</span>
            </div>`;
    }

    // Key metrics
    document.getElementById("metric-facts").textContent = formatNumber(data.metrics.total_facts);
    document.getElementById("metric-questions").textContent = formatNumber(data.metrics.total_questions);
    document.getElementById("metric-days").textContent = data.metrics.days_until_deadline;
}

/* ── Fact Collection ─────────────────────────────────────────────────────── */

function updateFacts(data) {
    document.getElementById("total-facts").textContent = formatNumber(data.total.count);
    document.getElementById("total-sources").textContent = formatNumber(data.sources.count);

    const bar = document.getElementById("overall-progress");
    const pct = Math.min(data.total.pct, 100);
    bar.style.width = pct + "%";
    bar.className = "progress-fill " + progressClass(pct);
    document.getElementById("overall-pct").textContent =
        formatNumber(data.total.count) + " / " + formatNumber(data.total.target) + " (" + pct + "%)";

    // Domain cards
    const grid = document.getElementById("domain-grid");
    grid.innerHTML = "";
    for (const d of data.domains) {
        const dpct = Math.min(d.pct, 100);
        grid.innerHTML += `
            <div class="domain-card">
                <div class="domain-header">
                    <span class="domain-name">${formatDomain(d.name)}</span>
                    <span class="domain-count">${formatNumber(d.count)} / ${formatNumber(d.target)}</span>
                </div>
                <div class="progress-bar">
                    <div class="progress-fill ${progressClass(dpct)}" style="width: ${dpct}%"></div>
                </div>
            </div>`;
    }

    // Country x Domain pivot table
    updatePivotTable(data);

    // Source distribution
    updateSourceDistribution(data);
}

function updatePivotTable(data) {
    const domainsList = data.domains_list || [];
    if (!data.pivot || data.pivot.length === 0) return;

    // Compute column maxes for heatmap (excluding General row and Total column)
    const colMax = {};
    for (const d of domainsList) {
        colMax[d] = 0;
        for (const row of data.pivot) {
            if (row.country !== "General" && (row[d] || 0) > colMax[d]) {
                colMax[d] = row[d];
            }
        }
    }

    // Header
    const header = document.getElementById("pivot-header");
    header.innerHTML = `<th class="country-col">Country</th>`;
    for (const d of domainsList) {
        header.innerHTML += `<th class="cell-value">${formatDomain(d)}</th>`;
    }
    header.innerHTML += `<th class="total-col">Total</th>`;

    // Body
    const tbody = document.getElementById("pivot-body");
    tbody.innerHTML = "";
    for (const row of data.pivot) {
        let tr = `<td class="country-col">${escapeHtml(row.country)}</td>`;
        for (const d of domainsList) {
            const val = row[d] || 0;
            if (val === 0) {
                tr += `<td class="cell-value cell-zero">\u2014</td>`;
            } else {
                const max = colMax[d] || 1;
                const opacity = Math.min(0.55, Math.log(val + 1) / Math.log(max + 1) * 0.55);
                tr += `<td class="cell-value" style="background:rgba(139,92,246,${opacity.toFixed(2)})">${formatNumber(val)}</td>`;
            }
        }
        tr += `<td class="cell-value total-col">${formatNumber(row.total)}</td>`;
        tbody.innerHTML += `<tr>${tr}</tr>`;
    }

    // Footer (totals)
    if (data.pivot_totals) {
        const foot = document.getElementById("pivot-footer");
        let tr = `<td class="country-col"><strong>Total</strong></td>`;
        for (const d of domainsList) {
            tr += `<td class="cell-value"><strong>${formatNumber(data.pivot_totals[d] || 0)}</strong></td>`;
        }
        tr += `<td class="cell-value total-col"><strong>${formatNumber(data.pivot_totals.total || 0)}</strong></td>`;
        foot.innerHTML = tr;
    }
}

function updateSourceDistribution(data) {
    const container = document.getElementById("source-distribution");
    if (!data.source_distribution || data.source_distribution.length === 0) {
        container.innerHTML = '<span style="color:var(--text-muted)">No source data</span>';
        return;
    }

    const maxCount = data.source_distribution[0].count;
    container.innerHTML = "";
    for (const src of data.source_distribution) {
        const widthPct = Math.max(2, (src.count / maxCount) * 100);
        container.innerHTML += `
            <div class="source-bar-row">
                <span class="source-bar-label">${escapeHtml(formatSourceType(src.type))}</span>
                <div class="source-bar-track">
                    <div class="source-bar-fill" style="width:${widthPct.toFixed(1)}%"></div>
                </div>
                <span class="source-bar-value">${formatNumber(src.count)}</span>
            </div>`;
    }
}

/* ── Upcoming Phases ────────────────────────────────────────────────────── */

function updatePhaseDetails(data) {
    const container = document.getElementById("phase-details");
    container.innerHTML = "";

    for (const phase of data.phases) {
        if (phase.id <= 1) continue; // Skip completed Phase 1

        const statusBadge = phase.status === "complete" ? "badge-complete" :
                           phase.status === "in_progress" ? "badge-in-progress" : "badge-not-started";
        const statusLabel = phase.status.replace(/_/g, " ");
        const isNext = phase.id === 2; // Phase 2 is next, open by default

        let subTasksHtml = "";
        if (phase.sub_tasks) {
            subTasksHtml = '<ul class="sub-task-list">';
            for (const st of phase.sub_tasks) {
                const stBadge = st.status === "complete" ? "badge-complete" :
                               st.status === "in_progress" ? "badge-in-progress" : "badge-not-started";
                const stIcon = st.status === "complete" ? "\u2713" : "\u25cb";
                subTasksHtml += `<li><span class="st-icon ${stBadge}">${stIcon}</span> ${escapeHtml(st.name)}</li>`;
            }
            subTasksHtml += "</ul>";
        }

        const deadlineHtml = phase.deadline ?
            `<div class="phase-deadline">Deadline: <strong>${phase.deadline}</strong></div>` : "";

        container.innerHTML += `
            <details ${isNext ? "open" : ""}>
                <summary>
                    <span class="phase-id">Phase ${phase.id}</span>
                    <span class="phase-title">${escapeHtml(phase.name)}</span>
                    <span class="badge ${statusBadge}">${statusLabel}</span>
                    <span class="phase-target">${escapeHtml(phase.target)}</span>
                </summary>
                <div class="phase-body">
                    <p>${escapeHtml(phase.details)}</p>
                    ${subTasksHtml}
                    ${deadlineHtml}
                </div>
            </details>`;
    }
}

/* ── Infrastructure Health ───────────────────────────────────────────────── */

function updateHealth(data) {
    const grid = document.getElementById("health-grid");
    grid.innerHTML = "";
    for (const svc of data.services) {
        let details = "";
        for (const [k, v] of Object.entries(svc.details || {})) {
            const label = k.replace(/_/g, " ");
            details += `<span>${label}: <strong>${escapeHtml(String(v))}</strong></span>`;
        }
        grid.innerHTML += `
            <div class="health-card">
                <div class="health-header">
                    <span class="status-dot ${svc.status}"></span>
                    <span class="service-name">${escapeHtml(svc.name)}</span>
                </div>
                <div class="health-detail">${details}</div>
            </div>`;
    }

    const tbody = document.getElementById("docker-table-body");
    tbody.innerHTML = "";
    if (data.docker_stats.length === 0) {
        tbody.innerHTML = '<tr><td colspan="3" style="color:var(--text-muted)">Docker stats unavailable</td></tr>';
        return;
    }
    for (const c of data.docker_stats) {
        const tr = document.createElement("tr");
        tr.innerHTML = `
            <td class="mono">${escapeHtml(c.container)}</td>
            <td class="mono">${escapeHtml(c.memory)}</td>
            <td class="mono">${escapeHtml(c.cpu)}</td>`;
        tbody.appendChild(tr);
    }
}

/* ── Main Loop ───────────────────────────────────────────────────────────── */

async function refresh() {
    const ts = document.getElementById("last-refresh");
    try {
        const [facts, project, health] = await Promise.all([
            fetchJSON("/api/facts"),
            fetchJSON("/api/project"),
            fetchJSON("/api/health"),
        ]);
        updateProject(project);
        updateFacts(facts);
        updatePhaseDetails(project);
        updateHealth(health);
        ts.textContent = "Last refresh: " + new Date().toLocaleTimeString();
    } catch (err) {
        ts.textContent = "Refresh failed: " + err.message;
    }
}

refresh();
setInterval(refresh, REFRESH_INTERVAL);
