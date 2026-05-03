/* OenoBench Review — vanilla JS, no build, no CDN.
 *
 * The Flask review route is server-render-first: it renders one question per
 * request. The form posts (form-encoded) to /submit-review, which upserts the
 * row and redirects back to /review/<batch> for the next question (or to
 * /complete/<batch> if the reviewer is done). Skip = navigate to next URL
 * without saving.
 */
(function () {
    'use strict';

    const form = document.getElementById('review-form');
    if (!form) return;

    const RUBRIC_KEYS = [
        'answer_correct', 'distractors_plausible', 'not_ambiguous',
        'source_faithful', 'needs_source', 'no_vague_language',
        'difficulty_match', 'cognitive_match', 'verbatim_copy',
        'wine_category_leak'
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

    /* ── Chip handling ──────────────────────────────────────────────────── */

    function setRubric(rubric, value) {
        const input = document.getElementById('input-' + rubric);
        if (!input) return;
        input.value = value;

        const row = document.querySelector('.rubric-row[data-rubric="' + rubric + '"]');
        if (!row) return;

        row.querySelectorAll('.chip').forEach(function (chip) {
            chip.classList.toggle('is-active', chip.dataset.value === value);
        });
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
        // Don't hijack typing in form fields.
        const tag = (e.target.tagName || '').toLowerCase();
        const isTextField = tag === 'input' || tag === 'textarea' || tag === 'select';

        if (e.key === 'Enter' && !isTextField) {
            e.preventDefault();
            updateTimeSpent();
            form.requestSubmit();
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

    /* ── Time tracking ──────────────────────────────────────────────────── */

    function updateTimeSpent() {
        const timeInput = document.getElementById('time-spent');
        if (!timeInput) return;
        const elapsed = Math.max(0, Math.floor((Date.now() - renderTsMs) / 1000));
        timeInput.value = String(elapsed);
    }

    setInterval(updateTimeSpent, 1000);
    form.addEventListener('submit', updateTimeSpent);

    /* ── Skip button ────────────────────────────────────────────────────── */

    const skipBtn = document.getElementById('skip-question');
    if (skipBtn) {
        skipBtn.addEventListener('click', function () {
            // Skip = leave without writing a review row. The IRR-aware ordering
            // already de-prioritises questions that have prior reviews, so the
            // user will simply see the next-best question on reload.
            window.location.href = '/review/' + encodeURIComponent(batchName);
        });
    }

    /* ── Auto-focus first rubric row on load ────────────────────────────── */
    const firstRow = document.querySelector('.rubric-row');
    if (firstRow) firstRow.focus();
})();
