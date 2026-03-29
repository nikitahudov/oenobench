/* OenoBench Dashboard — Client-side polling */

const REFRESH_INTERVAL = 30000;

async function fetchJSON(url) {
    const resp = await fetch(url);
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    return resp.json();
}

function formatNumber(n) {
    return n != null ? n.toLocaleString() : "—";
}

function progressClass(pct) {
    if (pct < 33) return "low";
    if (pct < 66) return "mid";
    return "high";
}

function formatDomain(name) {
    return name.replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase());
}

function timeAgo(isoStr) {
    if (!isoStr) return "—";
    const diff = (Date.now() - new Date(isoStr).getTime()) / 1000;
    if (diff < 60) return "just now";
    if (diff < 3600) return Math.floor(diff / 60) + "m ago";
    if (diff < 86400) return Math.floor(diff / 3600) + "h ago";
    return Math.floor(diff / 86400) + "d ago";
}

/* ── Fact Collection ─────────────────────────────────────────────────────── */

function updateFacts(data) {
    document.getElementById("total-facts").textContent = formatNumber(data.total.count);
    document.getElementById("total-sources").textContent = formatNumber(data.sources.count);
    document.getElementById("total-questions").textContent = formatNumber(data.questions.total);

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

    // Recent facts
    const tbody = document.getElementById("recent-facts-body");
    tbody.innerHTML = "";
    for (const f of data.recent_facts) {
        const tr = document.createElement("tr");
        tr.innerHTML = `
            <td class="truncate">${escapeHtml(f.fact_text)}</td>
            <td><span class="badge badge-complete">${formatDomain(f.domain)}</span></td>
            <td class="mono">${timeAgo(f.created_at)}</td>`;
        tbody.appendChild(tr);
    }
    if (data.recent_facts.length === 0) {
        tbody.innerHTML = '<tr><td colspan="3" style="color:var(--text-muted)">No facts yet</td></tr>';
    }
}

/* ── Scraper Status ──────────────────────────────────────────────────────── */

function updateScrapers(data) {
    document.getElementById("phase-name").textContent = data.phase.current;
    document.getElementById("scrapers-done").textContent =
        data.phase.completed_scrapers + " / " + data.phase.total_scrapers;

    const bar = document.getElementById("scraper-progress");
    const pct = Math.min(data.phase.pct, 100);
    bar.style.width = pct + "%";
    bar.className = "progress-fill " + progressClass(pct);
    document.getElementById("scraper-pct").textContent = pct + "%";

    const tbody = document.getElementById("scraper-table-body");
    tbody.innerHTML = "";
    data.scrapers.forEach((s, i) => {
        const badgeClass = s.status === "complete" ? "badge-complete" :
                          s.status === "in_progress" ? "badge-in-progress" : "badge-not-started";
        const statusLabel = s.status.replace(/_/g, " ");
        const tr = document.createElement("tr");
        tr.innerHTML = `
            <td class="mono">${i + 1}</td>
            <td>${escapeHtml(s.name)}</td>
            <td class="mono">${escapeHtml(s.file)}</td>
            <td><span class="badge ${badgeClass}">${statusLabel}</span></td>
            <td class="mono">${s.facts != null ? formatNumber(s.facts) : "—"}</td>`;
        tbody.appendChild(tr);
    });
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

    // Docker stats
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

/* ── Utilities ───────────────────────────────────────────────────────────── */

function escapeHtml(str) {
    const div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
}

/* ── Main Loop ───────────────────────────────────────────────────────────── */

async function refresh() {
    const ts = document.getElementById("last-refresh");
    try {
        const [facts, scrapers, health] = await Promise.all([
            fetchJSON("/api/facts"),
            fetchJSON("/api/scrapers"),
            fetchJSON("/api/health"),
        ]);
        updateFacts(facts);
        updateScrapers(scrapers);
        updateHealth(health);
        ts.textContent = "Last refresh: " + new Date().toLocaleTimeString();
    } catch (err) {
        ts.textContent = "Refresh failed: " + err.message;
    }
}

refresh();
setInterval(refresh, REFRESH_INTERVAL);
