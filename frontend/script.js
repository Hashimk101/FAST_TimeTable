// === Theme Toggling ===
const html = document.documentElement;
const themeToggleBtn = document.getElementById('theme-toggle');
const sunIcon = document.getElementById('sun-icon');
const moonIcon = document.getElementById('moon-icon');

// Persist theme preference
const savedTheme = localStorage.getItem('theme') || 'dark';
html.setAttribute('data-theme', savedTheme);
updateThemeIcon(savedTheme);

themeToggleBtn.addEventListener('click', () => {
    const current = html.getAttribute('data-theme');
    const next = current === 'dark' ? 'light' : 'dark';
    html.setAttribute('data-theme', next);
    localStorage.setItem('theme', next);
    updateThemeIcon(next);
    updateThemeColor(next);
});

function updateThemeIcon(theme) {
    sunIcon.style.display = theme === 'dark' ? 'block' : 'none';
    moonIcon.style.display = theme === 'light' ? 'block' : 'none';
}

// === Theme Color (address bar tint) ===
function updateThemeColor(theme) {
    const color = theme === 'dark' ? '#17130F' : '#FAF7F2';
    let meta = document.querySelector('meta[name="theme-color"]');
    if (!meta) {
        meta = document.createElement('meta');
        meta.name = 'theme-color';
        document.head.appendChild(meta);
    }
    meta.content = color;
}
updateThemeColor(savedTheme);

// === Live Clock ===
function updateClock() {
    const now = new Date();
    const h = now.getHours().toString().padStart(2, '0');
    const m = now.getMinutes().toString().padStart(2, '0');
    const days = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
    document.getElementById('now-text').textContent = `${days[now.getDay()]} ${h}:${m}`;
}
updateClock();
setInterval(updateClock, 10000);

// === Toast Notifications ===
function showToast(message, type = 'error', duration = 3000) {
    const container = document.getElementById('toast-container');
    if (!container) return;
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    let icon = '';
    if (type === 'error') {
        icon = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="8" x2="12" y2="12"></line><line x1="12" y1="16" x2="12.01" y2="16"></line></svg>`;
    }
    toast.innerHTML = `${icon} <span>${message}</span>`;
    container.appendChild(toast);
    setTimeout(() => {
        toast.classList.add('fade-out');
        toast.addEventListener('animationend', () => {
            toast.remove();
        });
    }, duration);
}

// === Modal Logic ===
const modal = document.getElementById('config-modal');
const openBtn = document.getElementById('open-config-btn');
const closeBtn = document.getElementById('close-config-btn');

function openModal() {
    initBatches();
    modal.classList.add('active');
    // Focus trap: move focus into modal
    const firstInput = modal.querySelector('select, input, button');
    if (firstInput) {
        // Prevent scroll avoids breaking the slide-up animation
        firstInput.focus({ preventScroll: true });
    }
}

function closeModal() {
    modal.classList.remove('active');
    // Return focus to trigger button
    openBtn.focus();
}

openBtn.addEventListener('click', openModal);
closeBtn.addEventListener('click', closeModal);
document.querySelectorAll('.empty-cta').forEach(btn => btn.addEventListener('click', openModal));

// Close on overlay click
modal.addEventListener('click', (e) => {
    if (e.target === modal) closeModal();
});

let modalTouchStartY = 0;
const modalContent = document.querySelector('.modal-content');
modalContent?.addEventListener('touchstart', (e) => {
    modalTouchStartY = e.touches[0].clientY;
}, { passive: true });
modalContent?.addEventListener('touchend', (e) => {
    const delta = e.changedTouches[0].clientY - modalTouchStartY;
    if (delta > 100 && modalTouchStartY < 150) closeModal(); // swipe down 100px to dismiss
});

// Focus trap: cycle focus within modal
modal.addEventListener('keydown', (e) => {
    if (e.key !== 'Tab') return;
    const focusable = modal.querySelectorAll('input, select, button, [tabindex]:not([tabindex="-1"])');
    if (focusable.length === 0) return;
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (e.shiftKey) {
        if (document.activeElement === first) { e.preventDefault(); last.focus(); }
    } else {
        if (document.activeElement === last) { e.preventDefault(); first.focus(); }
    }
});

// Close on Escape
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && modal.classList.contains('active')) {
        closeModal();
    }
});

// === Keyboard Shortcuts ===
document.addEventListener('keydown', (e) => {
    // Don't fire shortcuts when typing in inputs
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'SELECT' || e.target.tagName === 'TEXTAREA') return;
    // Don't hijack Ctrl/Cmd shortcuts (Ctrl+C = copy, etc.)
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    
    if (e.key === 'c' || e.key === 'C') {
        openModal();
    }
    if (e.key === 't' || e.key === 'T') {
        themeToggleBtn.click();
    }
});

// === Wizard Logic ===
const step1 = document.getElementById('step-1');
const step2 = document.getElementById('step-2');
const nextBtn = document.getElementById('next-step-btn');
const prevBtn = document.getElementById('prev-step-btn');
const repeatSection = document.getElementById('repeater-section');

let allSubjects = [];
let repeatCourses = [];

nextBtn.addEventListener('click', async () => {
    const batch = document.getElementById('batch-input').value;
    const course = document.getElementById('course-input').value;
    const section = document.getElementById('section-input').value.trim();

    if (!batch || !course || !section) {
        showToast("Please select your batch, course, and enter your section.");
        return;
    }

    // Move to step 2
    step1.classList.remove('active-step');
    step1.style.display = 'none';
    step2.style.display = 'block';
    step2.classList.add('active-step');

    // Focus trap
    const firstInput = step2.querySelector('button, input');
    if (firstInput) firstInput.focus();

    await loadStep2Data(batch, course);
});

prevBtn.addEventListener('click', () => {
    step2.classList.remove('active-step');
    step2.style.display = 'none';
    step1.style.display = 'block';
    step1.classList.add('active-step');
});

// Profile Selection visually
document.querySelectorAll('.profile-card').forEach(card => {
    card.addEventListener('click', (e) => {
        document.querySelectorAll('.profile-card').forEach(c => c.classList.remove('selected'));
        card.classList.add('selected');
        card.querySelector('input').checked = true;
    });
});


// === Binary Data Decoders ===
function decodeData(encodedStr) {
    try {
        if (!encodedStr) return null;
        const reversedStr = atob(encodedStr.trim());
        const jsonStr = reversedStr.split('').reverse().join('');
        return JSON.parse(jsonStr);
    } catch (e) {
        console.error("Failed to decode static binary data", e);
        return null;
    }
}

async function fetchDecoded(url, versionId = '') {
    try {
        const queryParam = versionId ? `?v=${encodeURIComponent(versionId)}` : `?t=${Date.now()}`;
        let res = await fetch(url + queryParam);
        // Fallback: if absolute path fails, try relative path (for local dev servers)
        if (!res.ok && url.startsWith('/')) {
            res = await fetch(url.slice(1) + queryParam);
        }
        if (!res.ok) return null;
        const text = await res.text();
        return decodeData(text);
    } catch (e) {
        // If absolute path threw, try relative
        if (url.startsWith('/')) {
            try {
                const queryParam = versionId ? `?v=${encodeURIComponent(versionId)}` : `?t=${Date.now()}`;
                const res = await fetch(url.slice(1) + queryParam);
                if (!res.ok) return null;
                const text = await res.text();
                return decodeData(text);
            } catch (_) {}
        }
        console.warn(`Could not load ${url}`, e);
        return null;
    }
}

function sanitizeSlug(name) {
    if (!name) return "ALL";
    return name.trim().replace(/[^a-zA-Z0-9_\-]/g, '_');
}

function parseTimeMinutes(timeStr) {
    try {
        let [h, m] = timeStr.split(':').map(Number);
        if (h >= 1 && h <= 7) h += 12;
        if (h === 8 && m < 30) h += 12; // 08:05 PM vs 08:30 AM
        return h * 60 + m;
    } catch (e) {
        return 0;
    }
}

async function initBatches() {
    try {
        let batches = await fetchDecoded('data/batches.bin');
        if (!batches) batches = await fetchDecoded('/data/batches.bin');
        const select = document.getElementById('batch-input');
        
        select.innerHTML = '<option value="" disabled selected>Select Batch</option>';

        if (batches && Array.isArray(batches)) {
            // Extract unique batch prefixes (e.g., "BS 25 CS" -> "BS 25")
            const seenPrefixes = new Set();
            batches.forEach(b => {
                if ((b.name.includes('BS') || b.name.includes('MS')) && !b.name.includes('Elective') && !b.name.includes('Repeat')) {
                    // Strip the last word (discipline) to get prefix like "BS 25" or "MS"
                    const parts = b.name.split(' ');
                    let prefix;
                    if (parts.length >= 3 && /^\d{2}$/.test(parts[1])) {
                        // "BS 25 CS" -> "BS 25"
                        prefix = parts.slice(0, 2).join(' ');
                    } else {
                        // "MS CS" -> "MS"
                        prefix = parts[0];
                    }

                    if (!seenPrefixes.has(prefix)) {
                        seenPrefixes.add(prefix);
                        const opt = document.createElement('option');
                        opt.value = prefix;
                        opt.textContent = prefix;
                        select.appendChild(opt);
                    }
                }
            });
            if (localStorage.getItem('batch')) {
                select.value = localStorage.getItem('batch');
            }
        }
    } catch (e) {
        console.error("Failed to load batches", e);
    }
}

async function loadStep2Data(batchName, courseName) {
    const profile = document.querySelector('input[name="student_profile"]:checked').value;
    const isRepeater = profile === 'repeater';
    const exactBatch = courseName ? `${batchName} ${courseName}`.trim() : batchName;

    try {
        // 1. Regular subjects from static data
        const allSubjectsMap = await fetchDecoded('/data/subjects.bin') || {};
        const regSubjects = allSubjectsMap[exactBatch] || allSubjectsMap[batchName] || allSubjectsMap['ALL'] || [];
        renderSubjects(regSubjects, 'subject-list', true);
        
        // 2. Electives (Only show for MS batches)
        const electivesSection = document.getElementById('electives-section');
        if (batchName.startsWith('MS')) {
            if (electivesSection) electivesSection.style.display = 'block';
            const electives = await fetchDecoded('/data/electives.bin') || [];
            renderSubjects(electives, 'electives-list', false);
        } else {
            if (electivesSection) electivesSection.style.display = 'none';
        }

        // 3. Repeater Data
        if (isRepeater) {
            repeatSection.style.display = 'flex';
            repeatSubjectsData = await fetchDecoded('/data/repeats.bin') || [];
            const repSelect = document.getElementById('repeat-subject-input');
            repSelect.innerHTML = '<option value="" disabled selected>Select Subject</option>';
            repeatSubjectsData.forEach(sub => {
                const opt = document.createElement('option');
                opt.value = sub.short_name;
                opt.dataset.name = sub.name;
                opt.textContent = sub.name;
                repSelect.appendChild(opt);
            });
            
            renderRepeatCourses();
        } else {
            repeatSection.style.display = 'none';
            repeatCourses = []; // Clear if they switched back to regular
        }
    } catch (e) {
        console.error("Failed to load step 2 data", e);
    }
}

function renderSubjects(subjects, containerId, precheck) {
    const listDiv = document.getElementById(containerId);
    listDiv.innerHTML = '';
    
    if (subjects.length === 0) {
        listDiv.innerHTML = '<div class="empty-repeat">No subjects found.</div>';
        return;
    }

    subjects.forEach(sub => {
        const label = document.createElement('label');
        label.className = `subject-item ${precheck ? 'checked' : ''}`;
        label.innerHTML = `
            <input type="checkbox" value="${sub.short_name}" data-name="${sub.name}" ${precheck ? 'checked' : ''}>
            <span>${sub.name}</span>
        `;
        
        const checkbox = label.querySelector('input');
        checkbox.addEventListener('change', () => {
            label.classList.toggle('checked', checkbox.checked);
            updateSubjectCount();
        });
        
        listDiv.appendChild(label);
    });
    updateSubjectCount();
}

function updateSubjectCount() {
    const count = document.querySelectorAll('#step-2 .subject-item input[type="checkbox"]:checked').length;
    const el = document.getElementById('subject-count');
    if (el) el.textContent = count === 0 ? '0 selected' : `${count} selected`;
}

// === Repeat Course Builder ===
let repeatSubjectsData = [];
const repeatDialog = document.getElementById('repeat-dialog');
document.getElementById('open-repeat-dialog-btn').addEventListener('click', () => {
    repeatDialog.style.display = 'block';
});
document.getElementById('close-repeat-dialog').addEventListener('click', () => {
    repeatDialog.style.display = 'none';
});

// When user picks a repeat subject, populate the section dropdown from repeats.bin data
document.getElementById('repeat-subject-input').addEventListener('change', (e) => {
    const sectionSelect = document.getElementById('repeat-section-input');
    const selectedVal = e.target.value;
    const selectedOption = e.target.options[e.target.selectedIndex];
    const selectedName = selectedOption ? selectedOption.dataset.name : '';

    const subjectData = repeatSubjectsData.find(s => 
        s.short_name === selectedVal || 
        s.name === selectedVal || 
        (selectedName && s.name === selectedName)
    );

    sectionSelect.innerHTML = '';

    const validSections = (subjectData && subjectData.sections) 
        ? subjectData.sections.filter(sec => sec && sec.trim()) 
        : [];

    if (validSections.length === 0) {
        // No specific sections for this subject — add a single "(All sections)" option
        sectionSelect.innerHTML = '<option value="" selected>(All sections)</option>';
        return;
    }

    // If multiple sections exist, add an "(All sections)" option at top
    if (validSections.length > 1) {
        const allOpt = document.createElement('option');
        allOpt.value = '';
        allOpt.textContent = '(All sections)';
        sectionSelect.appendChild(allOpt);
    }

    validSections.forEach(sec => {
        const opt = document.createElement('option');
        opt.value = sec.trim();
        opt.textContent = sec.trim();
        sectionSelect.appendChild(opt);
    });

    if (validSections.length === 1) {
        sectionSelect.selectedIndex = 0;
    }
});

document.getElementById('add-repeat-btn').addEventListener('click', () => {
    const subjSelect = document.getElementById('repeat-subject-input');
    const sectionSelect = document.getElementById('repeat-section-input');

    if (!subjSelect.value) {
        showToast("Please select a subject.");
        return;
    }

    const shortName = subjSelect.value;
    const subjName = subjSelect.options[subjSelect.selectedIndex].dataset.name;
    const section = sectionSelect.value; // e.g. "CS-A", "AI/DS", or ""

    repeatCourses.push({
        subject: shortName,
        name: subjName,
        section: section,
        displaySection: section || '(all)'
    });

    // Reset fields
    subjSelect.value = "";
    sectionSelect.innerHTML = '<option value="" disabled selected>Select a subject first</option>';
    repeatDialog.style.display = 'none';
    renderRepeatCourses();
});

function renderRepeatCourses() {
    const list = document.getElementById('repeat-chips-container');
    if (repeatCourses.length === 0) {
        list.innerHTML = '';
        return;
    }
    list.innerHTML = '';
    repeatCourses.forEach((rc, index) => {
        const chip = document.createElement('div');
        chip.className = 'repeat-chip';
        chip.innerHTML = `
            ${rc.subject} [${rc.displaySection}]
            <button type="button" class="remove-chip" onclick="removeRepeatCourse(${index})" aria-label="Remove">
                &times;
            </button>
        `;
        list.appendChild(chip);
    });
}

window.removeRepeatCourse = function(index) {
    repeatCourses.splice(index, 1);
    renderRepeatCourses();
};



// === Timetable Builder & Sync System ===

async function buildTimetableFromConfig(config, versionId = '') {
    if (!config) return null;
    const { batch, course, section, subjects = [], names = [], repeat_courses = [] } = config;
    const exactBatch = (course && !batch.includes(course)) ? `${batch} ${course}`.trim() : batch;

    let cosec = '';
    if (course && section) {
        cosec = section.startsWith(course + '-') ? section : `${course}-${section}`;
    } else if (course) {
        cosec = course;
    } else if (section) {
        cosec = section;
    }

    const primaryBatchSlug = sanitizeSlug(exactBatch);
    const cosecSlug = sanitizeSlug(cosec);

    const mergedTimetable = [[], [], [], [], [], []];

    // 1. Fetch primary section schedule
    const primaryFile = cosecSlug 
        ? `/data/schedules/${primaryBatchSlug}__${cosecSlug}.bin` 
        : `/data/schedules/${primaryBatchSlug}__.bin`;
    let primaryData = await fetchDecoded(primaryFile, versionId);
    if (!primaryData) {
        primaryData = await fetchDecoded(`/data/schedules/ALL__${cosecSlug}.bin`, versionId);
    }

    if (primaryData && Array.isArray(primaryData)) {
        for (let dayIdx = 0; dayIdx < 6; dayIdx++) {
            const dayClasses = primaryData[dayIdx] || [];
            const filtered = dayClasses.filter(c => subjects.includes(c.subject) || names.includes(c.subject));
            mergedTimetable[dayIdx].push(...filtered);
        }
    }

    // 2. Fetch repeat courses schedules
    for (const rc of repeat_courses) {
        const sectionSlug = sanitizeSlug(rc.section);
        const finalSectionPath = (sectionSlug === "ALL" || !sectionSlug) ? "" : sectionSlug;
        
        const repeatFileName = finalSectionPath 
            ? `BS_Repeat_Courses__${finalSectionPath}.bin` 
            : `BS_Repeat_Courses__.bin`;
        const rcData = await fetchDecoded(`/data/schedules/${repeatFileName}`, versionId);

        if (rcData && Array.isArray(rcData)) {
            for (let dayIdx = 0; dayIdx < 6; dayIdx++) {
                const dayClasses = rcData[dayIdx] || [];
                const filtered = dayClasses.filter(c => c.subject === rc.subject || c.subject === rc.name);
                mergedTimetable[dayIdx].push(...filtered);
            }
        }
    }

    // 3. Sort each day's entries by start time
    for (let dayIdx = 0; dayIdx < 6; dayIdx++) {
        mergedTimetable[dayIdx].sort((a, b) => parseTimeMinutes(a.start_time) - parseTimeMinutes(b.start_time));
    }

    return mergedTimetable;
}

let isSyncing = false;
let lastVersionCheckTimestamp = 0;
const VERSION_CHECK_COOLDOWN_MS = 2 * 60 * 1000; // 2 minutes

async function checkForTimetableUpdates(force = false) {
    if (isSyncing) return;
    const now = Date.now();
    if (!force && (now - lastVersionCheckTimestamp < VERSION_CHECK_COOLDOWN_MS)) return;
    
    const cachedConfigStr = localStorage.getItem('cachedConfig');
    if (!cachedConfigStr) return;

    let config;
    try {
        config = JSON.parse(cachedConfigStr);
    } catch {
        return;
    }

    isSyncing = true;
    lastVersionCheckTimestamp = now;

    try {
        let res;
        try {
            res = await fetch(`/data/version.json?t=${now}`, { cache: 'no-cache' });
            if (!res.ok) res = await fetch(`data/version.json?t=${now}`, { cache: 'no-cache' });
        } catch(e) {
            res = await fetch(`data/version.json?t=${now}`, { cache: 'no-cache' });
        }
        if (!res.ok) return;
        const versionData = await res.json();
        const serverVersion = versionData?.version;
        if (!serverVersion) return;

        const localVersion = localStorage.getItem('cachedTimetableVersion');
        if (localVersion && String(localVersion) === String(serverVersion)) {
            return; // No updates needed
        }

        const updatedTimetable = await buildTimetableFromConfig(config, serverVersion);
        if (!updatedTimetable) return;

        const oldTimetableStr = localStorage.getItem('cachedTimetable');
        const newTimetableStr = JSON.stringify(updatedTimetable);

        localStorage.setItem('cachedTimetable', newTimetableStr);
        localStorage.setItem('cachedTimetableVersion', String(serverVersion));

        if (oldTimetableStr !== newTimetableStr) {
            renderTimetable(updatedTimetable);
            renderMobileView(updatedTimetable);
            buildMobileWeekStrip();
            updateMobileDateText();
        }
    } catch (err) {
        console.warn('Background timetable sync check skipped:', err);
    } finally {
        isSyncing = false;
    }
}


// === Generate Timetable ===
const form = document.getElementById('config-form');
const gearSvg = `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><line x1="4" y1="21" x2="4" y2="14"></line><line x1="4" y1="10" x2="4" y2="3"></line><line x1="12" y1="21" x2="12" y2="12"></line><line x1="12" y1="8" x2="12" y2="3"></line><line x1="20" y1="21" x2="20" y2="16"></line><line x1="20" y1="12" x2="20" y2="3"></line><line x1="1" y1="14" x2="7" y2="14"></line><line x1="9" y1="8" x2="15" y2="8"></line><line x1="17" y1="16" x2="23" y2="16"></line></svg>`;

let lastConfig = null;

form.addEventListener('submit', async (e) => {
    e.preventDefault();
    
    const batch = document.getElementById('batch-input').value;
    const course = document.getElementById('course-input').value;
    const section = document.getElementById('section-input').value.trim().toUpperCase();
    
    // Gather primary courses
    const checkboxes = document.querySelectorAll('#step-2 .subject-item input[type="checkbox"]:checked');
    const selectedSubjects = Array.from(checkboxes).map(cb => cb.value);
    const selectedNames = Array.from(checkboxes).map(cb => cb.dataset.name);
    
    if (selectedSubjects.length === 0 && repeatCourses.length === 0) {
        showToast("Please select at least one course.");
        return;
    }

    // Step 1 Validation: Non-MS batches MUST have Discipline and Section
    if (!batch.startsWith("MS")) {
        if (!course || !section) {
            showToast("Please select both a Discipline and a Section for regular batches.");
            return;
        }
    }

    const btn = document.getElementById('generate-btn');
    btn.innerHTML = 'Generating...';
    btn.disabled = true;
    btn.style.opacity = '0.7';

    // Yield to the main thread so the UI can paint the "Generating..." state
    await new Promise(r => requestAnimationFrame(r));
    await new Promise(r => setTimeout(r, 0));

    // Issue #15: Show skeleton while loading
    if (typeof showMobileSkeleton === 'function') showMobileSkeleton();

    try {
        const currentConfig = {
            batch,
            course,
            section,
            subjects: selectedSubjects,
            names: selectedNames,
            repeat_courses: repeatCourses
        };

        const mergedTimetable = await buildTimetableFromConfig(currentConfig);
        
        if (mergedTimetable) {
            lastConfig = currentConfig;
            
            // Save preferences
            localStorage.setItem('batch', batch);
            localStorage.setItem('course', course);
            localStorage.setItem('section', section);

            // Cache timetable & config for offline use
            localStorage.setItem('cachedTimetable', JSON.stringify(mergedTimetable));
            localStorage.setItem('cachedConfig', JSON.stringify(lastConfig));

            // Fetch and record latest version in background
            const vNow = Date.now();
            fetch(`/data/version.json?t=${vNow}`, { cache: 'no-cache' })
                .then(r => r.ok ? r : fetch(`data/version.json?t=${vNow}`, { cache: 'no-cache' }))
                .then(r => r.ok ? r.json() : null)
                .catch(() => fetch(`data/version.json?t=${vNow}`, { cache: 'no-cache' }).then(r => r.ok ? r.json() : null))
                .then(v => {
                    if (v?.version) {
                        localStorage.setItem('cachedTimetableVersion', String(v.version));
                        lastVersionCheckTimestamp = Date.now();
                    }
                })
                .catch(() => {});

            renderTimetable(mergedTimetable);
            renderMobileView(mergedTimetable);
            
            // Combine names for status bar
            const allNames = [...selectedNames, ...repeatCourses.map(rc => rc.name)];
            const allSubs = [...selectedSubjects, ...repeatCourses.map(rc => rc.subject)];
            updateStatusBar(batch, course, section, allSubs, allNames);
            if (typeof renderMobileSubjectPills === 'function') renderMobileSubjectPills();

            // Hide offline banner if shown
            const offlineBanner = document.getElementById('offline-banner');
            if (offlineBanner) offlineBanner.style.display = 'none';
            
            // Update configure button
            openBtn.innerHTML = `${gearSvg} ${course}-${section}`;
            
            // Show grid, hide empty state
            document.getElementById('empty-state').style.display = 'none';
            document.getElementById('week-grid').style.display = 'grid';
            
            closeModal();
            
            // Reset wizard to step 1 for next time
            step2.classList.remove('active-step');
            step2.style.display = 'none';
            step1.style.display = 'block';
            step1.classList.add('active-step');
            
        } else {
            showToast('Failed to generate timetable data.');
            if (typeof hideMobileSkeleton === 'function') hideMobileSkeleton();
        }
    } catch (error) {
        // Offline fallback
        const cachedTimetable = localStorage.getItem('cachedTimetable');
        const cachedConfig = localStorage.getItem('cachedConfig');

        if (cachedTimetable && cachedConfig) {
            const timetable = JSON.parse(cachedTimetable);
            lastConfig = JSON.parse(cachedConfig);

            renderTimetable(timetable);
            renderMobileView(timetable);
            updateStatusBar(lastConfig.batch, lastConfig.course, lastConfig.section, lastConfig.subjects, lastConfig.names);
            if (typeof renderMobileSubjectPills === 'function') renderMobileSubjectPills();

            // Show offline banner
            const offlineBanner = document.getElementById('offline-banner');
            if (offlineBanner) offlineBanner.style.display = 'flex';

            openBtn.innerHTML = `${gearSvg} ${lastConfig.batch}-${lastConfig.course}-${lastConfig.section}`;
            document.getElementById('empty-state').style.display = 'none';
            document.getElementById('week-grid').style.display = 'grid';
            closeModal();
        } else {
            showToast('Failed to connect to API and no cached schedule found.');
            if (typeof hideMobileSkeleton === 'function') hideMobileSkeleton();
        }
    } finally {
        btn.innerHTML = 'Generate Timetable <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="9 18 15 12 9 6"></polyline></svg>';
        btn.disabled = false;
        btn.style.opacity = '1';
    }
});

// Load preferences on startup
window.addEventListener('DOMContentLoaded', () => {
    initBatches(); // Ensure batches are populated

    const savedBatch = localStorage.getItem('batch');
    const savedCourse = localStorage.getItem('course');
    const savedSection = localStorage.getItem('section');
    if (savedBatch) document.getElementById('batch-input').value = savedBatch;
    if (savedCourse) document.getElementById('course-input').value = savedCourse;
    if (savedSection) document.getElementById('section-input').value = savedSection;
    
    const cachedTimetable = localStorage.getItem('cachedTimetable');
    const cachedConfig = localStorage.getItem('cachedConfig');
    
    if (cachedTimetable && cachedConfig) {
        const timetable = JSON.parse(cachedTimetable);
        lastConfig = JSON.parse(cachedConfig);
        
        renderTimetable(timetable);
        renderMobileView(timetable);
        
        // Use allNames / allSubs to handle repeat courses if they exist
        const allNames = lastConfig.repeat_courses ? [...lastConfig.names, ...lastConfig.repeat_courses.map(rc => rc.name)] : lastConfig.names;
        const allSubs = lastConfig.repeat_courses ? [...lastConfig.subjects, ...lastConfig.repeat_courses.map(rc => rc.subject)] : lastConfig.subjects;
        
        updateStatusBar(lastConfig.batch, lastConfig.course, lastConfig.section, allSubs, allNames);
        if (typeof renderMobileSubjectPills === 'function') renderMobileSubjectPills();
        if (typeof restoreSubjectSelections === 'function') restoreSubjectSelections();
        
        openBtn.innerHTML = `${gearSvg} ${lastConfig.course}-${lastConfig.section}`;
        document.getElementById('empty-state').style.display = 'none';
        document.getElementById('week-grid').style.display = 'grid';
        closeModal();

        // Check for updates in background (0ms delay to user)
        checkForTimetableUpdates();
    } else {
        // Automatically open configure modal on first load
        openModal();
    }
});

// Re-check on tab focus / visibility change
document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible') {
        checkForTimetableUpdates();
    }
});
window.addEventListener('focus', () => {
    checkForTimetableUpdates();
});

function getSubjectColor(subject) {
    let hash = 0;
    for (let c of subject) hash = c.charCodeAt(0) + ((hash << 5) - hash);
    return colors[Math.abs(hash) % colors.length];
}

// === Status Bar ===
function updateStatusBar(batch, course, section, subjects, names) {
    const bar = document.getElementById('status-bar');
    const label = document.getElementById('status-label');
    const pills = document.getElementById('subject-pills');
    
    bar.style.display = 'block';
    label.textContent = `${batch}-${course}-${section}`;
    pills.innerHTML = '';
    
    subjects.forEach((sub, i) => {
        const color = getSubjectColor(sub);
        const pill = document.createElement('span');
        pill.className = 'pill';
        pill.style.setProperty('--card-bg', color.bg);
        pill.style.setProperty('--card-border', color.border);
        pill.innerHTML = `<span class="pill-dot"></span>${names[i] || sub}`;
        pills.appendChild(pill);
    });
}

// === Time Parsing ===
function parseTime(timeStr) {
    if (!timeStr) return 0;
    const parts = timeStr.split(':');
    if (parts.length < 2) return 8;
    let h = parseInt(parts[0], 10);
    const m = parseInt(parts[1], 10);
    if (h >= 1 && h <= 7) h += 12;
    if (h === 8 && m < 30) h += 12; // 08:05 PM vs 08:30 AM
    return h + (m / 60);
}

// === Color Palette ===
const colors = [
    { bg: 'var(--card-1)', border: 'var(--card-border-1)' },
    { bg: 'var(--card-2)', border: 'var(--card-border-2)' },
    { bg: 'var(--card-3)', border: 'var(--card-border-3)' },
    { bg: 'var(--card-4)', border: 'var(--card-border-4)' },
    { bg: 'var(--card-5)', border: 'var(--card-border-5)' }
];

// === Render Timetable ===
function updateDesktopTimetableCurrentState() {
    const now = new Date();
    const currentDecimal = now.getHours() + now.getMinutes() / 60;
    const todayDow = now.getDay();
    const todayTtIdx = (todayDow >= 1 && todayDow <= 6) ? todayDow - 1 : -1;

    document.querySelectorAll('.day-column').forEach((col, idx) => {
        if (idx === todayTtIdx) {
            col.classList.add('day-column--today');
            
            // clear old states
            col.querySelectorAll('.subject-card--current, .subject-card--upcoming').forEach(card => {
                card.classList.remove('subject-card--current', 'subject-card--upcoming');
            });
            
            let foundUpcoming = false;
            col.querySelectorAll('.subject-card').forEach(card => {
                const startVal = parseFloat(card.dataset.start);
                const endVal = parseFloat(card.dataset.end);
                
                if (startVal <= currentDecimal && endVal > currentDecimal) {
                    card.classList.add('subject-card--current');
                } else if (startVal > currentDecimal && !foundUpcoming) {
                    card.classList.add('subject-card--upcoming');
                    foundUpcoming = true;
                }
            });
        } else {
            col.classList.remove('day-column--today');
            col.querySelectorAll('.subject-card--current, .subject-card--upcoming').forEach(card => {
                card.classList.remove('subject-card--current', 'subject-card--upcoming');
            });
        }
    });
}

function renderTimetable(timetableData) {
    const days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
    const grid = document.getElementById('week-grid');
    const emptyState = document.getElementById('empty-state');
    
    if (emptyState) emptyState.style.display = 'none';
    if (grid) grid.style.display = 'grid';
    
    // Remove existing day columns
    document.querySelectorAll('.day-column').forEach(el => el.remove());

    timetableData.forEach((daySchedule, idx) => {
        const col = document.createElement('div');
        col.className = 'day-column';
        
        const now = new Date();
        const currentDecimal = now.getHours() + now.getMinutes() / 60;
        const todayDow = now.getDay();
        const todayTtIdx = (todayDow >= 1 && todayDow <= 6) ? todayDow - 1 : -1;
        
        if (idx === todayTtIdx) {
            col.classList.add('day-column--today');
        }
        col.innerHTML = `<div class="day-header">${days[idx]}</div>`;
        
        if (daySchedule.length === 0) {
            // Empty day placeholder
            const emptyMsg = document.createElement('div');
            emptyMsg.style.cssText = 'display:flex;align-items:center;justify-content:center;height:120px;color:var(--text-tertiary);font-size:0.75rem;font-weight:400;';
            emptyMsg.textContent = 'No classes';
            col.appendChild(emptyMsg);
        }
        
        [...daySchedule].sort((a, b) => parseTime(a.start_time) - parseTime(b.start_time)).forEach(cls => {
            const color = getSubjectColor(cls.subject);

            const startVal = parseTime(cls.start_time);
            const endVal = parseTime(cls.end_time);
            const duration = endVal - startVal;

            const card = document.createElement('article');
            card.className = 'subject-card';
            card.dataset.start = startVal;
            card.dataset.end = endVal;
            
            if (idx === todayTtIdx) {
                if (startVal <= currentDecimal && endVal > currentDecimal) {
                    card.classList.add('subject-card--current');
                } else if (startVal > currentDecimal && !col.querySelector('.subject-card--upcoming')) {
                    card.classList.add('subject-card--upcoming');
                }
            }
            card.style.setProperty('--start', startVal);
            card.style.setProperty('--duration', duration);
            card.style.setProperty('--card-bg', color.bg);
            card.style.setProperty('--card-border', color.border);
            
            card.innerHTML = `
                <div class="card-time">${formatTime12h(cls.start_time)} – ${formatTime12h(cls.end_time)}</div>
                <h3 class="card-title">${cls.subject}</h3>
                ${cls.status ? `<div class="card-status status-${cls.status.toLowerCase()}">${cls.status}</div>` : ''}
                <div class="card-location">
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"></path><circle cx="12" cy="10" r="3"></circle></svg>
                    ${cls.location}
                </div>
            `;
            col.appendChild(card);
        });
        
        grid.appendChild(col);
    });
}

// === Init ===
// loadSubjects(); (Removed to prevent ReferenceError halting execution)

// ===================================================================
// MOBILE UI — Agenda Timeline Renderer
// ===================================================================

let lastTimetableData = null; // Store for mobile re-renders
let mobileSelectedDay = null; // null = today. 0=Mon, 1=Tue, 2=Wed, 3=Thu, 4=Fri

// Wire mobile buttons to existing desktop functionality
document.getElementById('mobile-settings-btn')?.addEventListener('click', () => openModal());

// Mobile theme toggle syncs with desktop toggle
document.getElementById('mobile-theme-toggle')?.addEventListener('click', () => {
    themeToggleBtn.click(); // reuse desktop toggle
    syncMobileThemeIcons();
});

function syncMobileThemeIcons() {
    const theme = html.getAttribute('data-theme');
    const sun = document.querySelector('.m-sun');
    const moon = document.querySelector('.m-moon');
    if (sun) sun.style.display = theme === 'dark' ? 'block' : 'none';
    if (moon) moon.style.display = theme === 'light' ? 'block' : 'none';
}

// Sync icons on load
syncMobileThemeIcons();

// === Issue #1: Wire "Today" nav button ===
document.querySelector('.mobile-nav-btn[data-day="today"]')?.addEventListener('click', () => {
    mobileSelectedDay = null;
    buildMobileWeekStrip();
    updateMobileDateText();
    if (lastTimetableData) renderMobileView(lastTimetableData);
    document.querySelector('.mobile-timeline')?.scrollTo({ top: 0, behavior: 'smooth' });
    // Update active state
    document.querySelectorAll('.mobile-nav-btn').forEach(b => b.classList.remove('active'));
    document.querySelector('.mobile-nav-btn[data-day="today"]')?.classList.add('active');
});

// === Issue #2: Unified 12h time format ===
function formatTime12h(timeStr) {
    const parts = timeStr.split(':');
    let h = parseInt(parts[0], 10);
    const m = parseInt(parts[1] || '0', 10);
    // Map ambiguous 1-7 to PM (university classes)
    if (h >= 1 && h <= 7) h += 12;
    if (h === 8 && m < 30) h += 12; // 08:05 PM vs 08:30 AM
    const ampm = h >= 12 ? 'PM' : 'AM';
    const h12 = h > 12 ? h - 12 : (h === 0 ? 12 : h);
    const mStr = m.toString().padStart(2, '0');
    return `${h12}:${mStr} ${ampm}`;
}

// Spine labels use shorter format (no minutes if :00)
function formatTimeLabel(timeStr) {
    const parts = timeStr.split(':');
    let h = parseInt(parts[0], 10);
    const m = parts[1] || '00';
    if (h >= 1 && h <= 7) h += 12;
    const ampm = h >= 12 ? 'PM' : 'AM';
    const h12 = h > 12 ? h - 12 : (h === 0 ? 12 : h);
    return m === '00' ? `${h12} ${ampm}` : `${h12}:${m}`;
}

// === Issue #3: Mon-Fri only week strip ===
function buildMobileWeekStrip() {
    const strip = document.getElementById('mobile-week-strip');
    if (!strip) return;
    strip.innerHTML = '';

    const today = new Date();
    const todayDow = today.getDay(); // 0=Sun...6=Sat
    // Find this week's Monday (on Sunday, advance to next week's Monday)
    const monday = new Date(today);
    const offset = todayDow === 0 ? 1 : 1 - todayDow;
    monday.setDate(today.getDate() + offset);

    const dayNames = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];

    for (let i = 0; i < 6; i++) {
        const d = new Date(monday);
        d.setDate(monday.getDate() + i);
        const isToday = d.toDateString() === today.toDateString();
        // mobileSelectedDay: null=today, 0=Mon...5=Sat (matches timetable indices)
        const isActive = mobileSelectedDay === null ? isToday : (mobileSelectedDay === i);

        const el = document.createElement('div');
        el.className = 'mwd' + (isActive ? ' active' : '');
        el.innerHTML = `<span class="mwd-label">${dayNames[i]}</span><span class="mwd-num">${d.getDate()}</span>`;
        
        el.setAttribute('role', 'button');
        el.setAttribute('tabindex', '0');
        el.setAttribute('aria-pressed', isActive ? 'true' : 'false');
        
        const dayIndex = i;
        
        el.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                el.click();
            }
        });
        
        el.addEventListener('click', () => {
            mobileSelectedDay = dayIndex;
            const timeline = document.getElementById('mobile-timeline');
            if (timeline) {
                timeline.scrollTo({ top: 0, behavior: 'smooth' });
            }
            buildMobileWeekStrip();
            updateMobileDateText(dayIndex);
            if (lastTimetableData) renderMobileView(lastTimetableData);
        });
        strip.appendChild(el);
    }
}

// === Issue #11: Dynamic header date ===
function updateMobileDateText(selectedIdx) {
    const el = document.getElementById('mobile-date-text');
    if (!el) return;

    const today = new Date();
    const targetIdx = (selectedIdx !== undefined) ? selectedIdx : mobileSelectedDay;

    if (targetIdx === null) {
        // Show today's date
        el.textContent = today.toLocaleDateString('en-US', { weekday: 'long', month: 'short', day: 'numeric' });
        return;
    }

    // Calculate date for the selected weekday
    const todayDow = today.getDay();
    const monday = new Date(today);
    const offset = todayDow === 0 ? 1 : 1 - todayDow;
    monday.setDate(today.getDate() + offset);
    const selectedDate = new Date(monday);
    selectedDate.setDate(monday.getDate() + targetIdx);

    el.textContent = selectedDate.toLocaleDateString('en-US', { weekday: 'long', month: 'short', day: 'numeric' });
}

// Get current time as decimal hours
function getCurrentDecimalTime() {
    const now = new Date();
    return now.getHours() + now.getMinutes() / 60;
}

// === Issue #10: Swipe between days ===
let touchStartX = 0;
let touchStartY = 0;
document.getElementById('mobile-timeline')?.addEventListener('touchstart', (e) => {
    touchStartX = e.changedTouches[0].screenX;
    touchStartY = e.changedTouches[0].screenY;
}, { passive: true });

document.getElementById('mobile-timeline')?.addEventListener('touchend', (e) => {
    const deltaX = e.changedTouches[0].screenX - touchStartX;
    const deltaY = e.changedTouches[0].screenY - touchStartY;

    // Only trigger if horizontal swipe is dominant
    if (Math.abs(deltaX) < 60 || Math.abs(deltaY) > Math.abs(deltaX) * 0.7) return;

    const today = new Date();
    const todayDow = today.getDay();
    // Map today to timetable index (Mon=0...Sat=5), Sunday defaults to -1
    const todayTtIdx = (todayDow >= 1 && todayDow <= 6) ? todayDow - 1 : -1;
    const currentDay = mobileSelectedDay === null ? todayTtIdx : mobileSelectedDay;

    if (currentDay === -1) {
        if (deltaX < -60) mobileSelectedDay = 0; // Sunday → first swipe to Monday
        else return;
    } else if (deltaX < -60 && currentDay < 5) {
        // Swipe left → next day
        mobileSelectedDay = currentDay + 1;
    } else if (deltaX > 60 && currentDay > 0) {
        // Swipe right → prev day
        mobileSelectedDay = currentDay - 1;
    } else {
        return; // At boundary, don't re-render
    }

    const timeline = document.getElementById('mobile-timeline');
    if (timeline) {
        timeline.scrollTo({ top: 0 });
    }
    buildMobileWeekStrip();
    updateMobileDateText(mobileSelectedDay);
    if (lastTimetableData) renderMobileView(lastTimetableData);
}, { passive: true });

// === Issue #12: Contextual empty states ===
function getNextClassInfo(timetableData, fromDayIdx) {
    if (!timetableData) return null;
    const dayNames = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
    // Search from the next day onwards, wrapping around
    for (let offset = 1; offset <= 6; offset++) {
        const checkIdx = (fromDayIdx + offset) % 6;
        if (timetableData[checkIdx] && timetableData[checkIdx].length > 0) {
            const sorted = [...timetableData[checkIdx]].sort((a, b) => parseTime(a.start_time) - parseTime(b.start_time));
            return {
                subject: sorted[0].subject,
                time: formatTime12h(sorted[0].start_time),
                day: dayNames[checkIdx]
            };
        }
    }
    return null;
}

// === Issue #13: Subject pills on mobile ===
function renderMobileSubjectPills() {
    const container = document.getElementById('mobile-subject-pills');
    if (!container || !lastConfig) return;
    container.innerHTML = '';
    container.style.display = 'flex';

    lastConfig.names.forEach(name => {
        const pill = document.createElement('span');
        pill.className = 'm-subject-pill';
        pill.textContent = name;
        container.appendChild(pill);
    });
}

// === Issue #15: Skeleton loading ===
function showMobileSkeleton() {
    hideMobileSkeleton();
    const timeline = document.getElementById('mobile-timeline');
    if (!timeline) return;
    const empty = document.getElementById('mobile-empty-state');
    if (empty) empty.style.display = 'none';
    timeline.classList.remove('is-empty');

    // Clear existing
    timeline.querySelectorAll('.m-past, .m-now-divider, .m-hero-wrap, .m-up-wrap, .m-later, .m-skeleton').forEach(el => el.remove());

    const skeletonHTML = `
        <div class="m-skeleton">
            <div class="skeleton-block skeleton-hero"></div>
            <div class="skeleton-block skeleton-card"></div>
            <div class="skeleton-block skeleton-line"></div>
            <div class="skeleton-block skeleton-line"></div>
        </div>
    `;
    timeline.insertAdjacentHTML('beforeend', skeletonHTML);
}

function hideMobileSkeleton() {
    document.querySelectorAll('.m-skeleton').forEach(el => el.remove());
}

// === MAIN RENDER: Mobile agenda view for the selected day ===
function renderMobileView(timetableData) {
    lastTimetableData = timetableData;
    const timeline = document.getElementById('mobile-timeline');
    const emptyState = document.getElementById('mobile-empty-state');
    if (!timeline) return;

    hideMobileSkeleton();

    // Determine which day to show
    const today = new Date();
    const todayDow = today.getDay(); // 0=Sun...6=Sat
    // Map today to timetable index: Mon=0...Sat=5, Sunday=-1
    const todayTtIdx = (todayDow >= 1 && todayDow <= 6) ? todayDow - 1 : -1;
    // mobileSelectedDay is already 0=Mon...5=Sat or null (=today)
    const ttIdx = mobileSelectedDay === null ? todayTtIdx : mobileSelectedDay;

    // Clear previous content but keep empty state element
    timeline.querySelectorAll('.m-past, .m-now-divider, .m-hero-wrap, .m-up-wrap, .m-later').forEach(el => el.remove());

    if (ttIdx === -1 || !timetableData[ttIdx] || timetableData[ttIdx].length === 0) {
        timeline.classList.add('is-empty');
        emptyState.style.display = 'block';

        // Issue #12: Contextual empty state
        const isWeekend = ttIdx === -1;
        const nextInfo = getNextClassInfo(timetableData, isWeekend ? 5 : ttIdx);

        if (isWeekend) {
            emptyState.querySelector('h2').textContent = 'Enjoy your weekend!';
            emptyState.querySelector('p').textContent = nextInfo
                ? `Monday: ${nextInfo.subject} at ${nextInfo.time}`
                : 'No upcoming classes found.';
        } else {
            const dayNames = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
            emptyState.querySelector('h2').textContent = `No classes ${dayNames[ttIdx]}`;
            emptyState.querySelector('p').textContent = nextInfo
                ? `Next: ${nextInfo.subject} at ${nextInfo.time} ${nextInfo.day}`
                : 'No upcoming classes this week.';
        }
        return;
    }

    timeline.classList.remove('is-empty');
    emptyState.style.display = 'none';
    const classes = [...timetableData[ttIdx]].sort((a, b) => parseTime(a.start_time) - parseTime(b.start_time));
    const nowDecimal = getCurrentDecimalTime();
    const isViewingToday = (mobileSelectedDay === null && todayTtIdx >= 0) ||
                           (mobileSelectedDay !== null && mobileSelectedDay === todayTtIdx);

    // Categorize classes
    const past = [];
    let current = null;
    let upcoming = null;
    const later = [];

    classes.forEach(cls => {
        const start = parseTime(cls.start_time);
        const end = parseTime(cls.end_time);

        if (!isViewingToday) {
            later.push(cls);
        } else if (end <= nowDecimal) {
            past.push(cls);
        } else if (start <= nowDecimal && end > nowDecimal) {
            current = cls;
        } else if (!current && !upcoming && start > nowDecimal) {
            upcoming = cls;
        } else if (upcoming && start > nowDecimal) {
            later.push(cls);
        } else if (!upcoming) {
            upcoming = cls;
        } else {
            later.push(cls);
        }
    });

    if (!current && !upcoming && later.length > 0) {
        upcoming = later.shift();
    }

    const checkSvg = '<svg viewBox="0 0 24 24"><polyline points="20 6 9 17 4 12"/></svg>';
    const capSvg = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 10v6M2 10l10-5 10 5-10 5z"/><path d="M6 12v5c0 1.5 2.7 3 6 3s6-1.5 6-3v-5"/></svg>';

    // Render PAST (Issue #2: all times in 12h)
    past.forEach(cls => {
        const el = document.createElement('div');
        el.className = 'm-past';
        el.innerHTML = `
            <span class="mtl-label">${formatTimeLabel(cls.start_time)}</span>
            <span class="mtl-dot"></span>
            <div class="m-past-check">${checkSvg}</div>
            <div class="m-past-info">
                <div class="m-past-subject">${cls.subject}</div>
                ${cls.status ? `<div class="card-status status-${cls.status.toLowerCase()}">${cls.status}</div>` : ''}
                <div class="m-past-loc">${cls.location}</div>
            </div>
            <div class="m-past-time">${formatTime12h(cls.start_time)} – ${formatTime12h(cls.end_time)}</div>
        `;
        timeline.appendChild(el);
    });

    // Issue #8: Always render NOW divider when viewing today
    if (isViewingToday) {
        const nowDiv = document.createElement('div');
        nowDiv.className = 'm-now-divider';
        const h = today.getHours();
        const m = today.getMinutes().toString().padStart(2, '0');
        const ampm = h >= 12 ? 'PM' : 'AM';
        const h12 = h > 12 ? h - 12 : (h === 0 ? 12 : h);
        nowDiv.innerHTML = `<span class="m-now-label"><span class="m-now-pulse"></span>Now · ${h12}:${m} ${ampm}</span>`;
        timeline.appendChild(nowDiv);
    }

    // Render CURRENT (Hero Card) — Issue #2: 12h times
    if (current) {
        const start = parseTime(current.start_time);
        const end = parseTime(current.end_time);
        const progress = Math.min(100, Math.max(0, ((nowDecimal - start) / (end - start)) * 100));

        const el = document.createElement('div');
        el.className = 'm-hero-wrap';
        el.innerHTML = `
            <span class="mtl-label">${formatTimeLabel(current.start_time)}</span>
            <span class="mtl-dot"></span>
            <div class="m-hero-card">
                <div class="m-hero-badge">${capSvg} Current</div>
                <div class="m-hero-subject-row">
                    <span class="m-pulse-dot"></span>
                    <span class="m-hero-subject">${current.subject}</span>
                </div>
                ${current.status ? `<div class="card-status status-${current.status.toLowerCase()}">${current.status}</div>` : ''}
                <div class="m-hero-section">${lastConfig ? lastConfig.course + '-' + lastConfig.section : ''}</div>
                <div class="m-hero-times">
                    <span>${formatTime12h(current.start_time)}</span>
                    <span>${formatTime12h(current.end_time)}</span>
                </div>
                <div class="m-hero-loc">Location: <strong>${current.location}</strong></div>
                <div class="m-prog-track"><div class="m-prog-fill" style="width:${progress}%"></div></div>
            </div>
        `;
        timeline.appendChild(el);
    }

    // Render UPCOMING (Clean Card) — Issue #2: 12h, Issue #6: countdown
    if (upcoming) {
        const upStart = parseTime(upcoming.start_time);
        const minsUntil = Math.ceil((upStart - nowDecimal) * 60);
        const countdownHtml = (isViewingToday && minsUntil > 0 && minsUntil <= 30)
            ? `<span class="m-up-countdown">Starts in ${minsUntil}m</span>`
            : '';
        const badgeText = isViewingToday ? 'Upcoming' : 'First';

        const el = document.createElement('div');
        el.className = 'm-up-wrap';
        el.innerHTML = `
            <span class="mtl-label">${formatTimeLabel(upcoming.start_time)}</span>
            <span class="mtl-dot"></span>
            <div class="m-up-card">
                <div class="m-up-badge">${badgeText}</div>
                ${countdownHtml}
                <div class="m-up-time">${formatTime12h(upcoming.start_time)} – ${formatTime12h(upcoming.end_time)}</div>
                <div class="m-up-subject">${upcoming.subject}</div>
                ${upcoming.status ? `<div class="card-status status-${upcoming.status.toLowerCase()}">${upcoming.status}</div>` : ''}
                <div class="m-up-detail">${upcoming.location}</div>
            </div>
        `;
        timeline.appendChild(el);
    }

    // Render LATER (Text only) — Issue #2: 12h
    later.forEach(cls => {
        const el = document.createElement('div');
        el.className = 'm-later';
        el.innerHTML = `
            <span class="mtl-label">${formatTimeLabel(cls.start_time)}</span>
            <span class="mtl-dot"></span>
            <div class="m-later-time">${formatTime12h(cls.start_time)} – ${formatTime12h(cls.end_time)}</div>
            <div class="m-later-subject">${cls.subject}</div>
            ${cls.status ? `<div class="card-status status-${cls.status.toLowerCase()}">${cls.status}</div>` : ''}
            <div class="m-later-loc">${cls.location}</div>
        `;
        timeline.appendChild(el);
    });
}

// Init mobile UI
buildMobileWeekStrip();
updateMobileDateText();

// Refresh mobile view every minute to keep current/upcoming accurate & sync if sheet changed
setInterval(() => {
    if (lastTimetableData) {
        renderMobileView(lastTimetableData);
        updateDesktopTimetableCurrentState();
    }
    updateMobileDateText();
    checkForTimetableUpdates();
}, 60000);





// === Side Drawer Menu & Free Rooms ===
(function() {
    const drawerOverlay = document.getElementById('drawer-overlay');
    const sideDrawer = document.getElementById('side-drawer');
    const openDrawerDesktopBtn = document.getElementById('menu-toggle-btn');
    const openDrawerMobileBtn = document.getElementById('mobile-menu-btn');
    const closeDrawerBtn = document.getElementById('close-drawer-btn');
    const roomsModal = document.getElementById('rooms-modal');
    const closeRoomsModalBtn = document.getElementById('close-rooms-modal-btn');
    const findRoomsBtn = document.getElementById('find-rooms-btn');
    const timeSlotSelect = document.getElementById('time-slot-select');
    const blockBtns = document.querySelectorAll('#rooms-modal [data-block]');
    const dayBtns = document.querySelectorAll('#rooms-modal [data-day]');
    const roomsResultsContainer = document.getElementById('rooms-results-container');
    const roomsGrid = document.getElementById('rooms-grid');
    const resultsCountBadge = document.getElementById('results-count-badge');
    const resultsContextLabel = document.getElementById('results-context-label');

    let selectedBlock = 'C';
    let selectedDay = 'Monday';
    let cachedRoomsData = null;

    function openDrawer() {
        drawerOverlay?.classList.add('active');
        drawerOverlay?.setAttribute('aria-hidden', 'false');
    }
    function closeDrawer() {
        drawerOverlay?.classList.remove('active');
        drawerOverlay?.setAttribute('aria-hidden', 'true');
    }

    openDrawerDesktopBtn?.addEventListener('click', openDrawer);
    openDrawerMobileBtn?.addEventListener('click', openDrawer);
    closeDrawerBtn?.addEventListener('click', closeDrawer);
    drawerOverlay?.addEventListener('click', (e) => { if (e.target === drawerOverlay) closeDrawer(); });

    // Swipe right to dismiss
    let touchStartX = 0;
    sideDrawer?.addEventListener('touchstart', (e) => { touchStartX = e.touches[0].clientX; }, { passive: true });
    sideDrawer?.addEventListener('touchend', (e) => { if (e.changedTouches[0].clientX - touchStartX > 75) closeDrawer(); });

    // Nav item: Export PNG
    document.getElementById('nav-item-export')?.addEventListener('click', () => {
        closeDrawer();
        if (typeof generateTimetablePNG === 'function') {
            generateTimetablePNG();
        } else {
            showToast('Please configure a schedule first.', 'error');
        }
    });

    // Nav item: Find Free Rooms
    document.getElementById('nav-item-rooms')?.addEventListener('click', () => {
        closeDrawer();
        openRoomsModal();
    });

    // Nav item: Configure
    document.getElementById('nav-item-config')?.addEventListener('click', () => {
        closeDrawer();
        openModal();
    });

    // Nav item: Theme
    const navThemeStatus = document.getElementById('nav-theme-status');
    function syncThemeLabel() {
        const t = document.documentElement.getAttribute('data-theme') || 'dark';
        if (navThemeStatus) navThemeStatus.textContent = t === 'dark' ? 'Dark' : 'Light';
    }
    syncThemeLabel();
    document.getElementById('nav-item-theme')?.addEventListener('click', () => {
        document.getElementById('theme-toggle')?.click();
        syncThemeLabel();
    });

    // --- Free Rooms Modal ---
    function openRoomsModal() {
        initRoomDefaults();
        roomsModal?.classList.add('active');
    }
    function closeRoomsModal() {
        roomsModal?.classList.remove('active');
    }
    closeRoomsModalBtn?.addEventListener('click', closeRoomsModal);
    roomsModal?.addEventListener('click', (e) => { if (e.target === roomsModal) closeRoomsModal(); });

    function initRoomDefaults() {
        const dayNames = ['Sunday','Monday','Tuesday','Wednesday','Thursday','Friday','Saturday'];
        const today = dayNames[new Date().getDay()];
        selectedDay = (today === 'Sunday' || today === 'Saturday') ? 'Monday' : today;
        dayBtns.forEach(b => {
            const active = b.dataset.day === selectedDay;
            b.classList.toggle('active', active);
            b.setAttribute('aria-checked', active ? 'true' : 'false');
        });
        const now = new Date();
        const mins = now.getHours() * 60 + now.getMinutes();
        const slots = [
            {v:'08:30 - 09:50',e:590},{v:'10:00 - 11:20',e:680},{v:'11:30 - 12:50',e:770},
            {v:'01:00 - 02:20',e:860},{v:'02:30 - 03:50',e:950},{v:'03:55 - 05:15',e:1035}
        ];
        const match = slots.find(s => mins <= s.e);
        if (match && timeSlotSelect) timeSlotSelect.value = match.v;
        if (roomsResultsContainer) roomsResultsContainer.style.display = 'none';
    }

    blockBtns.forEach(btn => btn.addEventListener('click', () => {
        blockBtns.forEach(b => { b.classList.remove('active'); b.setAttribute('aria-checked','false'); });
        btn.classList.add('active'); btn.setAttribute('aria-checked','true');
        selectedBlock = btn.dataset.block;
    }));
    dayBtns.forEach(btn => btn.addEventListener('click', () => {
        dayBtns.forEach(b => { b.classList.remove('active'); b.setAttribute('aria-checked','false'); });
        btn.classList.add('active'); btn.setAttribute('aria-checked','true');
        selectedDay = btn.dataset.day;
    }));

    findRoomsBtn?.addEventListener('click', async () => {
        const slot = timeSlotSelect?.value || '08:30 - 09:50';
        const [sStr, eStr] = slot.split(' - ');
        const slotStart = parseTime(sStr);
        const slotEnd = parseTime(eStr);

        if (!cachedRoomsData) {
            findRoomsBtn.textContent = 'Scanning...';
            findRoomsBtn.disabled = true;
            cachedRoomsData = await fetchDecoded('data/rooms.bin') || await fetchDecoded('/data/rooms.bin');
            findRoomsBtn.textContent = 'Find Rooms';
            findRoomsBtn.disabled = false;
        }
        if (!cachedRoomsData) { showToast('Failed to load room data.'); return; }

        const blockRooms = cachedRoomsData.rooms.filter(r => r.startsWith(selectedBlock + '-'));
        const dayOcc = cachedRoomsData.occupied[selectedDay] || {};
        const freeRooms = blockRooms.filter(room => {
            const classes = dayOcc[room] || [];
            return !classes.some(c => Math.max(slotStart, parseTime(c.s)) < Math.min(slotEnd, parseTime(c.e)));
        });

        roomsResultsContainer.style.display = 'block';
        resultsCountBadge.textContent = freeRooms.length + ' Free';
        resultsContextLabel.textContent = 'Block ' + selectedBlock + ' · ' + selectedDay.slice(0,3) + ' · ' + slot;
        roomsGrid.innerHTML = freeRooms.length === 0
            ? '<div style="grid-column:1/-1;text-align:center;padding:24px;color:var(--text-tertiary);font-size:0.82rem">No free rooms found.</div>'
            : freeRooms.map(r => '<div class="room-chip">' + r + '</div>').join('');
    });

    // Keyboard shortcuts
    document.addEventListener('keydown', (e) => {
        if (e.target.tagName === 'INPUT' || e.target.tagName === 'SELECT' || e.target.tagName === 'TEXTAREA') return;
        if (e.key === 'Escape') {
            if (drawerOverlay?.classList.contains('active')) { closeDrawer(); return; }
            if (roomsModal?.classList.contains('active')) { closeRoomsModal(); return; }
        }
        if (e.key === 'm' || e.key === 'M') {
            drawerOverlay?.classList.contains('active') ? closeDrawer() : openDrawer();
        }
    });
})();

// === PNG Timetable Exporter (Mobile Wallpaper & High-Res Portrait Edition) ===
function generateTimetablePNG() {
    if (!lastConfig) { showToast('Please configure a schedule first.', 'error'); return; }
    const cachedTtStr = localStorage.getItem('cachedTimetable');
    if (!cachedTtStr) { showToast('No timetable data found.', 'error'); return; }
    const timetable = JSON.parse(cachedTtStr);

    const scale = 2; // 2x multiplier on 1080x2340 = 2160x4680 (ultra crisp retina mobile wallpaper)
    const baseW = 1080, baseH = 2340;
    const w = baseW * scale, h = baseH * scale;
    const canvas = document.createElement('canvas');
    canvas.width = w; canvas.height = h;
    const ctx = canvas.getContext('2d', { alpha: false });

    // Safe polyfill for roundRect on older engines
    if (!ctx.roundRect) {
        ctx.roundRect = function(rx, ry, rw, rh, rad) {
            this.rect(rx, ry, rw, rh);
            return this;
        };
    }

    // Background
    ctx.fillStyle = '#ffffff';
    ctx.fillRect(0, 0, w, h);

    const padX = 36 * scale, padY = 48 * scale;

    // Helper functions
    function format12(timeStr) {
        if (!timeStr) return '';
        const realH = Math.floor(parseTime(timeStr));
        const parts = timeStr.split(':');
        const m = parts[1] || '00';
        const ampm = realH >= 12 ? 'PM' : 'AM';
        const H12 = realH % 12 || 12;
        return `${H12}:${m} ${ampm}`;
    }

    function formatHour12(hourNum) {
        const ampm = hourNum >= 12 ? 'PM' : 'AM';
        const H12 = hourNum % 12 || 12;
        return `${H12}:00 ${ampm}`;
    }

    function wrapText(context, text, maxWidth) {
        const words = text.split(' ');
        const lines = [];
        let currentLine = words[0];
        for (let i = 1; i < words.length; i++) {
            const word = words[i];
            const width = context.measureText(currentLine + ' ' + word).width;
            if (width < maxWidth) { currentLine += ' ' + word; }
            else { lines.push(currentLine); currentLine = word; }
        }
        lines.push(currentLine);
        return lines;
    }

    // 1. TOP HEADER CARD (Dark Theme)
    const headerX = padX, headerY = padY;
    const headerW = w - padX * 2, headerH = 130 * scale;

    ctx.fillStyle = '#0b0f19';
    ctx.beginPath();
    ctx.roundRect(headerX, headerY, headerW, headerH, 20 * scale);
    ctx.fill();

    // Geometric Flower/Crest Icon
    const iconCenterX = headerX + 44 * scale;
    const iconCenterY = headerY + headerH / 2;
    const iconR = 18 * scale;
    ctx.save();
    ctx.strokeStyle = '#a78bfa';
    ctx.lineWidth = 1.75 * scale;
    for (let angle = 0; angle < Math.PI; angle += Math.PI / 3) {
        ctx.beginPath();
        ctx.ellipse(iconCenterX, iconCenterY, iconR, iconR * 0.45, angle, 0, Math.PI * 2);
        ctx.stroke();
    }
    ctx.restore();

    // Header Title
    ctx.fillStyle = '#ffffff';
    ctx.font = 'bold ' + (22 * scale) + 'px system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif';
    ctx.textAlign = 'left';
    ctx.textBaseline = 'middle';
    ctx.fillText('FAST NUCES ISLAMABAD', headerX + 80 * scale, iconCenterY);

    // Header Right Badge (Batch / Section)
    const nameParts = [lastConfig.batch, lastConfig.course, lastConfig.section].filter(p => p && p.trim() !== '');
    const nameStr = nameParts.length > 2 
        ? `${nameParts[0]} ${nameParts[1]} - ${nameParts[2]}`
        : nameParts.join(' ');

    ctx.font = 'bold ' + (18 * scale) + 'px system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif';
    const badgeTextW = ctx.measureText(nameStr).width;
    const badgeW = badgeTextW + (54 * scale);
    const badgeH = 46 * scale;
    const badgeX = headerX + headerW - badgeW - (20 * scale);
    const badgeY = headerY + (headerH - badgeH) / 2;

    ctx.fillStyle = '#1e293b';
    ctx.beginPath();
    ctx.roundRect(badgeX, badgeY, badgeW, badgeH, 12 * scale);
    ctx.fill();
    ctx.strokeStyle = '#334155';
    ctx.lineWidth = 1.5 * scale;
    ctx.stroke();

    ctx.fillStyle = '#f8fafc';
    ctx.textAlign = 'left';
    ctx.fillText(nameStr, badgeX + (16 * scale), headerY + headerH / 2);

    // Small Calendar Icon on Badge
    const calX = badgeX + badgeW - (28 * scale);
    const calY = headerY + headerH / 2 - (8 * scale);
    ctx.strokeStyle = '#94a3b8';
    ctx.lineWidth = 1.75 * scale;
    ctx.strokeRect(calX, calY, 16 * scale, 16 * scale);
    ctx.beginPath();
    ctx.moveTo(calX, calY + 5 * scale);
    ctx.lineTo(calX + 16 * scale, calY + 5 * scale);
    ctx.stroke();

    // 2. FOOTER CARD (Stats & Quote)
    const footerW = w - padX * 2;
    const footerH = 120 * scale;
    const footerX = padX;
    const footerY = h - padY - footerH;

    // Count statistics
    let theoryCount = 0, labCount = 0;
    timetable.forEach(day => day.forEach(cls => {
        const isLab = cls.subject.toLowerCase().includes('lab') || (parseTime(cls.end_time) - parseTime(cls.start_time) >= 2.5);
        if (isLab) labCount++; else theoryCount++;
    }));

    ctx.fillStyle = '#ffffff';
    ctx.beginPath();
    ctx.roundRect(footerX, footerY, footerW, footerH, 18 * scale);
    ctx.fill();
    ctx.strokeStyle = '#e2e8f0';
    ctx.lineWidth = 1.5 * scale;
    ctx.stroke();

    // Legend items on left
    let legendCursorX = footerX + 24 * scale;
    const legendCenterY = footerY + footerH / 2;

    // Theory Indicator
    ctx.fillStyle = '#a855f7';
    ctx.beginPath();
    ctx.arc(legendCursorX, legendCenterY - 10 * scale, 6 * scale, 0, Math.PI * 2);
    ctx.fill();
    ctx.fillStyle = '#1e293b';
    ctx.font = 'bold ' + (15 * scale) + 'px system-ui, sans-serif';
    ctx.textAlign = 'left';
    ctx.fillText('Theory', legendCursorX + 12 * scale, legendCenterY - 10 * scale);
    ctx.fillStyle = '#64748b';
    ctx.font = '500 ' + (13 * scale) + 'px system-ui, sans-serif';
    ctx.fillText(theoryCount + ' Classes', legendCursorX + 12 * scale, legendCenterY + 12 * scale);
    legendCursorX += 140 * scale;

    // Lab Indicator
    if (labCount > 0) {
        ctx.fillStyle = '#f97316';
        ctx.beginPath();
        ctx.arc(legendCursorX, legendCenterY - 10 * scale, 6 * scale, 0, Math.PI * 2);
        ctx.fill();
        ctx.fillStyle = '#1e293b';
        ctx.font = 'bold ' + (15 * scale) + 'px system-ui, sans-serif';
        ctx.fillText('Lab', legendCursorX + 12 * scale, legendCenterY - 10 * scale);
        ctx.fillStyle = '#64748b';
        ctx.font = '500 ' + (13 * scale) + 'px system-ui, sans-serif';
        ctx.fillText(labCount + ' ' + (labCount === 1 ? 'Class' : 'Classes'), legendCursorX + 12 * scale, legendCenterY + 12 * scale);
    }

    // Motivational Quote on right
    ctx.textAlign = 'right';
    ctx.fillStyle = '#475569';
    ctx.font = '600 ' + (16 * scale) + 'px system-ui, sans-serif';
    ctx.fillText('✨ Stay consistent, great things take time!', footerX + footerW - 24 * scale, legendCenterY);

    // 3. TIMETABLE GRID DIMENSIONS
    const gridTop = headerY + headerH + 28 * scale;
    const gridBottom = footerY - 24 * scale;
    const gridH = gridBottom - gridTop;
    const gridW = w - padX * 2;

    const timeColW = 100 * scale;
    const days = ['MONDAY', 'TUESDAY', 'WEDNESDAY', 'THURSDAY', 'FRIDAY', 'SATURDAY'];
    const dayColW = (gridW - timeColW) / 6;

    // Determine time range
    let minHour = 8;
    let maxHour = 18; // Default 6:00 PM
    timetable.forEach(d => d.forEach(c => {
        const s = parseTime(c.start_time), e = parseTime(c.end_time);
        if (s > 0 && Math.floor(s) < minHour) minHour = Math.floor(s);
        if (e > 0 && Math.ceil(e) > maxHour) maxHour = Math.ceil(e);
    }));

    const totalHours = maxHour - minHour;
    const dayHdrH = 56 * scale;
    const bodyH = gridH - dayHdrH;
    const hourH = bodyH / totalHours;

    // Top Header: TIME Pill + Days
    const timePillW = 76 * scale, timePillH = 34 * scale;
    const timePillX = padX + (timeColW - timePillW) / 2;
    const timePillY = gridTop + (dayHdrH - timePillH) / 2;
    ctx.fillStyle = '#f1f5f9';
    ctx.beginPath();
    ctx.roundRect(timePillX, timePillY, timePillW, timePillH, 10 * scale);
    ctx.fill();
    ctx.fillStyle = '#475569';
    ctx.font = 'bold ' + (14 * scale) + 'px system-ui, sans-serif';
    ctx.textAlign = 'center';
    ctx.fillText('TIME', timePillX + timePillW / 2, timePillY + timePillH / 2);

    // Day Headers
    ctx.fillStyle = '#334155';
    ctx.font = 'bold ' + (15 * scale) + 'px system-ui, sans-serif';
    for (let i = 0; i < 6; i++) {
        const cx = padX + timeColW + i * dayColW;
        ctx.fillText(days[i], cx + dayColW / 2, gridTop + dayHdrH / 2);
    }

    // Grid Divider under headers
    ctx.strokeStyle = '#e2e8f0';
    ctx.lineWidth = 1.5 * scale;
    ctx.beginPath();
    ctx.moveTo(padX, gridTop + dayHdrH);
    ctx.lineTo(padX + gridW, gridTop + dayHdrH);
    ctx.stroke();

    // Time Axis and Horizontal Hour Grid Lines
    for (let hIndex = 0; hIndex <= totalHours; hIndex++) {
        const curHour = minHour + hIndex;
        const lineY = gridTop + dayHdrH + hIndex * hourH;

        // Left Time Label
        ctx.fillStyle = '#64748b';
        ctx.font = 'bold ' + (14 * scale) + 'px system-ui, sans-serif';
        ctx.textAlign = 'center';
        ctx.fillText(formatHour12(curHour), padX + timeColW / 2, lineY);

        // Grid Horizontal Line across days
        ctx.strokeStyle = '#f1f5f9';
        ctx.lineWidth = 1.25 * scale;
        ctx.beginPath();
        ctx.moveTo(padX + timeColW, lineY);
        ctx.lineTo(padX + gridW, lineY);
        ctx.stroke();
    }

    // Vertical day separators
    for (let i = 1; i < 6; i++) {
        const sepX = padX + timeColW + i * dayColW;
        ctx.strokeStyle = '#f8fafc';
        ctx.lineWidth = 1.25 * scale;
        ctx.beginPath();
        ctx.moveTo(sepX, gridTop + dayHdrH);
        ctx.lineTo(sepX, gridBottom);
        ctx.stroke();
    }

    // 4. COLOR PALETTES FOR CLASS CARDS
    const palettes = [
        { bg: '#f5f3ff', border: '#ddd6fe', title: '#4c1d95', pillBg: '#ede9fe', pillText: '#6d28d9', room: '#5b21b6' }, // Lavender Theory
        { bg: '#fdf2f8', border: '#fbcfe8', title: '#831843', pillBg: '#fce7f3', pillText: '#be185d', room: '#9d174d' }, // Rose Pink
        { bg: '#eff6ff', border: '#bfdbfe', title: '#1e3a8a', pillBg: '#dbeafe', pillText: '#1d4ed8', room: '#1e40af' }, // Sky Blue
        { bg: '#f0fdf4', border: '#bbf7d0', title: '#14532d', pillBg: '#dcfce7', pillText: '#15803d', room: '#166534' }  // Mint Green
    ];
    const labPalette = { bg: '#fff7ed', border: '#fed7aa', title: '#7c2d12', pillBg: '#ffedd5', pillText: '#c2410c', room: '#9a3412' }; // Warm Peach Lab

    // 5. DRAW CLASS CARDS
    timetable.forEach((daySchedule, di) => {
        const colX = padX + timeColW + di * dayColW;

        daySchedule.forEach(cls => {
            const sH = parseTime(cls.start_time), eH = parseTime(cls.end_time);
            if (sH === 0 || eH === 0) return;

            const sy = gridTop + dayHdrH + (sH - minHour) * hourH;
            const ch = (eH - sH) * hourH;

            const isLab = cls.subject.toLowerCase().includes('lab') || (eH - sH >= 2.5);
            let col = labPalette;
            if (!isLab) {
                let hash = 0;
                for (let i = 0; i < cls.subject.length; i++) hash = cls.subject.charCodeAt(i) + ((hash << 5) - hash);
                col = palettes[Math.abs(hash) % palettes.length];
            }

            const cardPad = 4 * scale;
            const rx = colX + cardPad;
            const ry = sy + 2 * scale;
            const rw = dayColW - cardPad * 2;
            const rh = ch - 4 * scale;

            // Card Body
            ctx.fillStyle = col.bg;
            ctx.beginPath();
            ctx.roundRect(rx, ry, rw, rh, 10 * scale);
            ctx.fill();
            ctx.strokeStyle = col.border;
            ctx.lineWidth = 1.5 * scale;
            ctx.stroke();

            // Inside Card: Top Time Pill
            const timePillHeight = 22 * scale;
            const timePillWidth = rw - 12 * scale;
            const timePillPosX = rx + 6 * scale;
            const timePillPosY = ry + 6 * scale;

            ctx.fillStyle = col.pillBg;
            ctx.beginPath();
            ctx.roundRect(timePillPosX, timePillPosY, timePillWidth, timePillHeight, 6 * scale);
            ctx.fill();

            ctx.fillStyle = col.pillText;
            ctx.font = 'bold ' + (11 * scale) + 'px system-ui, sans-serif';
            ctx.textAlign = 'center';
            ctx.textBaseline = 'middle';
            ctx.fillText(format12(cls.start_time) + ' - ' + format12(cls.end_time), rx + rw / 2, timePillPosY + timePillHeight / 2);

            // Inside Card: Subject Title
            ctx.fillStyle = col.title;
            ctx.font = 'bold ' + (15 * scale) + 'px system-ui, sans-serif';
            const lines = wrapText(ctx, cls.subject, rw - 14 * scale);
            const lh = 18 * scale;
            const textBlockH = lines.length * lh;
            const availCenter = (rh - timePillHeight - (24 * scale));
            let titleStartY = ry + timePillHeight + (availCenter - textBlockH) / 2 + 10 * scale;

            lines.forEach(line => {
                ctx.fillText(line, rx + rw / 2, titleStartY);
                titleStartY += lh;
            });

            // Inside Card: Room Location
            ctx.fillStyle = col.room;
            ctx.font = '600 ' + (13 * scale) + 'px system-ui, sans-serif';
            ctx.fillText(cls.location || '', rx + rw / 2, ry + rh - 12 * scale);
        });
    });

    // 6. EXPORT / SHARE HANDLER (Native Share on Mobile + Direct Download Fallback)
    canvas.toBlob(async (blob) => {
        if (!blob) return;
        const cleanName = nameStr.replace(/[^a-zA-Z0-9]/g, '_');
        const fileName = 'FAST_Timetable_' + cleanName + '.png';
        const file = new File([blob], fileName, { type: 'image/png' });

        // If Web Share API is available (Mobile devices: iOS Safari, Android Chrome)
        if (navigator.canShare && navigator.canShare({ files: [file] })) {
            try {
                await navigator.share({
                    files: [file],
                    title: 'FAST NUCES Timetable',
                    text: `${nameStr} Timetable Graphic`
                });
                showToast('Shared successfully!', 'info');
                return;
            } catch (err) {
                if (err.name === 'AbortError') return; // User simply closed the share sheet
            }
        }

        // Fallback: Standard browser download (Desktop)
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = fileName;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
        showToast('Timetable exported!', 'info');
    }, 'image/png', 1.0);
}
