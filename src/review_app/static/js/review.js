/* OenoBench Review — vanilla JS, no build, no CDN.
 *
 * Server-render-first: one question per request. Form posts (form-encoded) to
 * /submit-review, which upserts and redirects to /review/<batch> for the next
 * question. Skip POSTs to /skip-question, which appends the question_id to a
 * per-session skip list and redirects.
 */
(function () {
    'use strict';

    const form = document.getElementById('review-form');
    if (!form) return;

    const RUBRIC_KEYS = [
        'answer_correct', 'distractors_plausible', 'not_ambiguous',
        'source_faithful', 'needs_source', 'no_vague_language',
        'labels_correct', 'verbatim_copy'
    ];

    // Number keys → rubric value mapping. 4 = explicit Skip (clears row).
    const KEY_TO_VALUE = {
        '1': 'pass',
        '2': 'warn',
        '3': 'fail',
        '4': ''
    };

    const renderTsMs = parseInt(form.dataset.renderTs, 10) || Date.now();
    const batchName = form.dataset.batchName;
    const questionId = form.dataset.questionId;
    const STORAGE_KEY = 'reviewApp:' + questionId;

    /* ── Chip handling ──────────────────────────────────────────────────── */

    function setRubric(rubric, value, opts) {
        const input = document.getElementById('input-' + rubric);
        if (!input) return;
        input.value = value;

        const row = document.querySelector('.rubric-row[data-rubric="' + rubric + '"]');
        if (!row) return;

        row.querySelectorAll('.chip').forEach(function (chip) {
            chip.classList.toggle('is-active', chip.dataset.value === value);
        });

        if (!opts || !opts.silent) saveState();
    }

    document.querySelectorAll('.chip').forEach(function (chip) {
        chip.addEventListener('click', function (e) {
            e.preventDefault();
            const rubric = chip.dataset.rubric;
            const value = chip.dataset.value;
            setRubric(rubric, value);
            const row = document.querySelector('.rubric-row[data-rubric="' + rubric + '"]');
            if (row) row.focus();
        });
    });

    /* ── Tooltip toggles ────────────────────────────────────────────────── */

    document.querySelectorAll('.rubric-help-btn').forEach(function (btn) {
        btn.addEventListener('click', function (e) {
            e.preventDefault();
            e.stopPropagation();
            const id = btn.dataset.target;
            const tip = document.getElementById(id);
            if (!tip) return;
            tip.hidden = !tip.hidden;
        });
    });

    /* ── Show-all-tips toggle ───────────────────────────────────────────── */

    const tipsToggle = document.getElementById('toggle-all-tips');
    if (tipsToggle) {
        tipsToggle.addEventListener('click', function () {
            const opening = tipsToggle.dataset.state !== 'open';
            document.querySelectorAll('.rubric-tip').forEach(function (tip) {
                tip.hidden = !opening;
            });
            tipsToggle.dataset.state = opening ? 'open' : 'closed';
            tipsToggle.textContent = opening ? 'Hide definitions' : 'Show definitions';
            tipsToggle.setAttribute('aria-pressed', opening ? 'true' : 'false');
        });
    }

    /* ── Keyboard shortcuts ─────────────────────────────────────────────── */

    function focusedRubricRow() {
        const active = document.activeElement;
        if (!active) return null;
        if (active.classList && active.classList.contains('rubric-row')) {
            return active;
        }
        return active.closest ? active.closest('.rubric-row') : null;
    }

    function focusByOffset(delta) {
        const rows = Array.from(document.querySelectorAll('.rubric-row'));
        if (!rows.length) return;
        const current = focusedRubricRow();
        let idx = current ? rows.indexOf(current) : -1;
        idx = (idx + delta + rows.length) % rows.length;
        rows[idx].focus();
    }

    document.addEventListener('keydown', function (e) {
        const tag = (e.target.tagName || '').toLowerCase();
        const isTextField = tag === 'input' || tag === 'textarea' || tag === 'select';

        // V → focus verdict select (only when not typing in a field).
        if (!isTextField && (e.key === 'v' || e.key === 'V')) {
            const verdict = document.getElementById('overall-verdict');
            if (verdict) {
                e.preventDefault();
                verdict.focus();
                return;
            }
        }

        if (e.key === 'Enter' && !isTextField) {
            e.preventDefault();
            updateTimeSpent();
            if (!form.querySelector('#submit-review').disabled) {
                form.requestSubmit();
            }
            return;
        }

        const row = focusedRubricRow();
        if (!row) return;

        if (Object.prototype.hasOwnProperty.call(KEY_TO_VALUE, e.key)) {
            e.preventDefault();
            setRubric(row.dataset.rubric, KEY_TO_VALUE[e.key]);
            return;
        }

        if (e.key === 'Escape') {
            e.preventDefault();
            setRubric(row.dataset.rubric, '');
            return;
        }

        if (e.key === 'Tab') {
            e.preventDefault();
            focusByOffset(e.shiftKey ? -1 : 1);
        }
    });

    document.querySelectorAll('.rubric-row').forEach(function (row) {
        row.addEventListener('focus', function () {
            document.querySelectorAll('.rubric-row.is-focused')
                .forEach(function (r) { r.classList.remove('is-focused'); });
            row.classList.add('is-focused');
        });
        row.addEventListener('blur', function () {
            row.classList.remove('is-focused');
        });
    });

    /* ── Submit gate ────────────────────────────────────────────────────── */

    const verdictSelect = document.getElementById('overall-verdict');
    const submitBtn = document.getElementById('submit-review');

    function updateSubmitGate() {
        if (!submitBtn || !verdictSelect) return;
        const ok = !!verdictSelect.value;
        submitBtn.disabled = !ok;
        submitBtn.title = ok ? '' : 'Pick a verdict to submit';
    }

    if (verdictSelect) {
        verdictSelect.addEventListener('change', function () {
            updateSubmitGate();
            saveState();
        });
    }

    /* ── Notes auto-grow ────────────────────────────────────────────────── */

    const notes = document.getElementById('review-notes');
    function autoGrowNotes() {
        if (!notes) return;
        notes.style.height = 'auto';
        const max = parseFloat(getComputedStyle(notes).maxHeight) || 288;
        notes.style.height = Math.min(notes.scrollHeight, max) + 'px';
    }
    if (notes) {
        notes.addEventListener('input', function () {
            autoGrowNotes();
            saveState();
        });
    }

    /* ── Suggested answer / difficulty change → autosave ────────────────── */

    const suggestedAnswer = document.getElementById('suggested-answer');
    const suggestedDifficulty = document.getElementById('suggested-difficulty');
    if (suggestedAnswer) suggestedAnswer.addEventListener('input', saveState);
    if (suggestedDifficulty) suggestedDifficulty.addEventListener('change', saveState);

    /* ── LocalStorage autosave / restore ────────────────────────────────── */

    function readState() {
        const state = { rubrics: {} };
        RUBRIC_KEYS.forEach(function (k) {
            const inp = document.getElementById('input-' + k);
            state.rubrics[k] = inp ? inp.value : '';
        });
        state.verdict = verdictSelect ? verdictSelect.value : '';
        state.suggested_answer = suggestedAnswer ? suggestedAnswer.value : '';
        state.suggested_difficulty = suggestedDifficulty ? suggestedDifficulty.value : '';
        state.notes = notes ? notes.value : '';
        return state;
    }

    function saveState() {
        try {
            localStorage.setItem(STORAGE_KEY, JSON.stringify(readState()));
        } catch (err) {
            // Quota or disabled storage — silently ignore.
        }
    }

    function clearState() {
        try { localStorage.removeItem(STORAGE_KEY); } catch (err) { /* ignore */ }
    }

    function restoreState() {
        let raw;
        try { raw = localStorage.getItem(STORAGE_KEY); } catch (err) { return; }
        if (!raw) return;
        let s;
        try { s = JSON.parse(raw); } catch (err) { return; }
        if (!s || typeof s !== 'object') return;

        if (s.rubrics) {
            RUBRIC_KEYS.forEach(function (k) {
                const v = s.rubrics[k];
                if (typeof v === 'string') setRubric(k, v, { silent: true });
            });
        }
        if (verdictSelect && typeof s.verdict === 'string') verdictSelect.value = s.verdict;
        if (suggestedAnswer && typeof s.suggested_answer === 'string') suggestedAnswer.value = s.suggested_answer;
        if (suggestedDifficulty && typeof s.suggested_difficulty === 'string') suggestedDifficulty.value = s.suggested_difficulty;
        if (notes && typeof s.notes === 'string') {
            notes.value = s.notes;
            autoGrowNotes();
        }
    }

    /* ── Time tracking with idle pause ──────────────────────────────────── */

    const IDLE_MS = 60 * 1000;
    let accumulatedSeconds = 0;
    let lastTickMs = Date.now();
    let lastActivityMs = Date.now();

    function tickTime() {
        const now = Date.now();
        const idle = (now - lastActivityMs) > IDLE_MS;
        if (!idle) {
            accumulatedSeconds += (now - lastTickMs) / 1000;
        }
        lastTickMs = now;
        const timeInput = document.getElementById('time-spent');
        if (timeInput) timeInput.value = String(Math.max(0, Math.floor(accumulatedSeconds)));
    }

    function updateTimeSpent() {
        // Snap the timer to "now" before submit so the hidden field is fresh.
        tickTime();
    }

    function bumpActivity() {
        // If we were idle, reset lastTickMs so we don't credit the idle gap.
        const now = Date.now();
        if ((now - lastActivityMs) > IDLE_MS) lastTickMs = now;
        lastActivityMs = now;
    }

    ['keydown', 'mousedown', 'mousemove', 'scroll', 'touchstart']
        .forEach(function (ev) {
            window.addEventListener(ev, bumpActivity, { passive: true });
        });

    // Seed accumulated seconds from initial render timestamp so a slow first
    // pageload still starts the counter sensibly.
    accumulatedSeconds = Math.max(0, (Date.now() - renderTsMs) / 1000);
    lastTickMs = Date.now();
    setInterval(tickTime, 1000);

    form.addEventListener('submit', function () {
        updateTimeSpent();
        clearState();
    });

    /* ── Skip button → POST /skip-question ──────────────────────────────── */

    const skipBtn = document.getElementById('skip-question');
    if (skipBtn) {
        skipBtn.addEventListener('click', function () {
            clearState();
            const skipForm = document.createElement('form');
            skipForm.method = 'POST';
            skipForm.action = '/skip-question';
            skipForm.style.display = 'none';

            const batchInput = document.createElement('input');
            batchInput.type = 'hidden';
            batchInput.name = 'batch_name';
            batchInput.value = batchName;
            skipForm.appendChild(batchInput);

            const qidInput = document.createElement('input');
            qidInput.type = 'hidden';
            qidInput.name = 'question_id';
            qidInput.value = questionId;
            skipForm.appendChild(qidInput);

            document.body.appendChild(skipForm);
            skipForm.submit();
        });
    }

    /* ── Init ───────────────────────────────────────────────────────────── */

    restoreState();
    updateSubmitGate();
    autoGrowNotes();

    const firstRow = document.querySelector('.rubric-row');
    if (firstRow) firstRow.focus();
})();
