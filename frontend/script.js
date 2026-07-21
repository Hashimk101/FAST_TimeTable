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

// === Modal Logic ===
const modal = document.getElementById('config-modal');
const openBtn = document.getElementById('open-config-btn');
const closeBtn = document.getElementById('close-config-btn');

function openModal() {
    modal.classList.add('active');
    // Focus trap: move focus into modal
    const firstInput = modal.querySelector('select, input, button');
    if (firstInput) setTimeout(() => firstInput.focus(), 200);
}

function closeModal() {
    modal.classList.remove('active');
    // Return focus to trigger button
    openBtn.focus();
}

openBtn.addEventListener('click', openModal);
closeBtn.addEventListener('click', closeModal);

// Close on overlay click
modal.addEventListener('click', (e) => {
    if (e.target === modal) closeModal();
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

// === Search Subjects ===
const searchInput = document.getElementById('subject-search');
searchInput.addEventListener('input', (e) => {
    const text = e.target.value.toLowerCase();
    document.querySelectorAll('.subject-item').forEach(item => {
        const name = item.querySelector('span').innerText.toLowerCase();
        item.style.display = name.includes(text) ? 'flex' : 'none';
    });
});

// === Fetch Subjects ===
let allSubjects = [];
async function loadSubjects() {
    try {
        const res = await fetch('/api/subjects');
        const data = await res.json();
        
        if (data.status === 'success') {
            allSubjects = data.data;
            renderSubjectsList();
            restoreSubjectSelections();
        } else {
            console.error('Failed to load subjects:', data.message);
        }
    } catch (e) {
        console.error('Error fetching subjects:', e);
        document.getElementById('subject-list').innerHTML = 
            '<div style="padding:20px;text-align:center;color:var(--text-secondary);font-size:0.85rem;">Could not connect to the server.<br>Is <code>app.py</code> running?</div>';
    }
}

// === Restore Subject Selections from Cache ===
function restoreSubjectSelections() {
    if (!lastConfig?.subjects) return;
    document.querySelectorAll('.subject-item input').forEach(cb => {
        if (lastConfig.subjects.includes(cb.value)) {
            cb.checked = true;
            cb.closest('.subject-item').classList.add('checked');
        }
    });
    updateSubjectCount();
}

function renderSubjectsList() {
    const listDiv = document.getElementById('subject-list');
    listDiv.innerHTML = '';
    
    allSubjects.forEach(sub => {
        const label = document.createElement('label');
        label.className = 'subject-item';
        label.innerHTML = `
            <input type="checkbox" value="${sub.short_name}">
            <span>${sub.name}</span>
        `;
        
        // Toggle the "checked" highlight class
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
    const count = document.querySelectorAll('.subject-item input[type="checkbox"]:checked').length;
    const el = document.getElementById('subject-count');
    el.textContent = count === 0 ? '0 selected' : `${count} selected`;
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
    
    if (!section) {
        alert("Please enter your section.");
        return;
    }
    
    const checkboxes = document.querySelectorAll('.subject-item input[type="checkbox"]:checked');
    const selectedSubjects = Array.from(checkboxes).map(cb => cb.value);
    const selectedNames = Array.from(checkboxes).map(cb => cb.parentElement.querySelector('span').innerText);
    
    if (selectedSubjects.length === 0) {
        alert("Please select at least one subject.");
        return;
    }

    const btn = document.getElementById('generate-btn');
    btn.innerHTML = 'Generating...';
    btn.disabled = true;
    btn.style.opacity = '0.7';

    // Issue #15: Show skeleton while loading
    if (typeof showMobileSkeleton === 'function') showMobileSkeleton();
    // Clear subject checkbox UI for re-generation
    document.querySelectorAll('.subject-item input[type="checkbox"]').forEach(cb => {
        cb.checked = false;
        cb.closest('.subject-item')?.classList.remove('checked');
    });

    try {
        const res = await fetch('/api/timetable', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ batch, course, section, subjects: selectedSubjects })
        });
        const data = await res.json();
        
        if (data.status === 'success') {
            lastConfig = { batch, course, section, subjects: selectedSubjects, names: selectedNames };
            
            // Save preferences
            localStorage.setItem('batch', batch);
            localStorage.setItem('course', course);
            localStorage.setItem('section', section);

            // Issue #4: Cache timetable for offline use
            localStorage.setItem('cachedTimetable', JSON.stringify(data.timetable));
            localStorage.setItem('cachedConfig', JSON.stringify(lastConfig));

            renderTimetable(data.timetable);
            renderMobileView(data.timetable);
            updateStatusBar(batch, course, section, selectedSubjects, selectedNames);
            if (typeof renderMobileSubjectPills === 'function') renderMobileSubjectPills();

            // Hide offline banner if shown
            const offlineBanner = document.getElementById('offline-banner');
            if (offlineBanner) offlineBanner.style.display = 'none';
            
            // Update configure button
            openBtn.innerHTML = `${gearSvg} ${batch}-${course}-${section}`;
            
            // Show grid, hide empty state
            document.getElementById('empty-state').style.display = 'none';
            document.getElementById('week-grid').style.display = 'grid';
            
            closeModal();
        } else {
            alert('Error: ' + data.message);
            if (typeof hideMobileSkeleton === 'function') hideMobileSkeleton();
        }
    } catch (error) {
        // Issue #4: Offline fallback — try loading from cache
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
            alert('Failed to connect to API and no cached schedule found.');
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
        updateStatusBar(lastConfig.batch, lastConfig.course, lastConfig.section, lastConfig.subjects, lastConfig.names);
        if (typeof renderMobileSubjectPills === 'function') renderMobileSubjectPills();
        restoreSubjectSelections();
        
        openBtn.innerHTML = `${gearSvg} ${lastConfig.batch}-${lastConfig.course}-${lastConfig.section}`;
        document.getElementById('empty-state').style.display = 'none';
        document.getElementById('week-grid').style.display = 'grid';
        closeModal();
    } else {
        // Automatically open configure modal on first load
        openModal();
    }
});

// === Status Bar ===
function updateStatusBar(batch, course, section, subjects, names) {
    const bar = document.getElementById('status-bar');
    const label = document.getElementById('status-label');
    const pills = document.getElementById('subject-pills');
    
    bar.style.display = 'block';
    label.textContent = `${batch}-${course}-${section}`;
    pills.innerHTML = '';
    
    subjects.forEach((sub, i) => {
        const colorIdx = i % colors.length;
        const pill = document.createElement('span');
        pill.className = 'pill';
        pill.style.setProperty('--card-bg', colors[colorIdx].bg);
        pill.style.setProperty('--card-border', colors[colorIdx].border);
        pill.innerHTML = `<span class="pill-dot"></span>${names[i] || sub}`;
        pills.appendChild(pill);
    });
}

// === Time Parsing ===
function parseTime(timeStr) {
    const parts = timeStr.split(':');
    if (parts.length < 2) return 8;
    let h = parseInt(parts[0], 10);
    const m = parseInt(parts[1], 10);
    if (h >= 1 && h <= 7) h += 12;
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
function renderTimetable(timetableData) {
    const days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday'];
    const grid = document.getElementById('week-grid');
    
    // Remove existing day columns
    document.querySelectorAll('.day-column').forEach(el => el.remove());

    let colorIndex = 0;
    const subjectColors = {};

    // Count total classes for empty-day messaging
    let totalClasses = 0;

    timetableData.forEach((daySchedule, idx) => {
        const col = document.createElement('div');
        col.className = 'day-column';
        
        const now = new Date();
        const currentDecimal = now.getHours() + now.getMinutes() / 60;
        const todayDow = now.getDay();
        const todayTtIdx = (todayDow >= 1 && todayDow <= 5) ? todayDow - 1 : -1;
        
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
            totalClasses++;
            if (!subjectColors[cls.subject]) {
                subjectColors[cls.subject] = colors[colorIndex % colors.length];
                colorIndex++;
            }

            const startVal = parseTime(cls.start_time);
            const endVal = parseTime(cls.end_time);
            const duration = endVal - startVal;

            const card = document.createElement('article');
            card.className = 'subject-card';
            
            if (idx === todayTtIdx) {
                if (startVal <= currentDecimal && endVal > currentDecimal) {
                    card.classList.add('subject-card--current');
                } else if (startVal > currentDecimal && !col.querySelector('.subject-card--upcoming')) {
                    card.classList.add('subject-card--upcoming');
                }
            }
            card.style.setProperty('--start', startVal);
            card.style.setProperty('--duration', duration);
            card.style.setProperty('--card-bg', subjectColors[cls.subject].bg);
            card.style.setProperty('--card-border', subjectColors[cls.subject].border);
            
            card.innerHTML = `
                <h3>${cls.subject}</h3>
                <p class="card-time">${formatTime12h(cls.start_time)} – ${formatTime12h(cls.end_time)}</p>
                <p class="card-location">
                    <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"></path><circle cx="12" cy="10" r="3"></circle></svg>
                    ${cls.location}
                </p>
            `;
            col.appendChild(card);
        });
        
        grid.appendChild(col);
    });
}

// === Init ===
loadSubjects();

// ===================================================================
// MOBILE UI — Agenda Timeline Renderer
// ===================================================================

let lastTimetableData = null; // Store for mobile re-renders
let mobileSelectedDay = null; // null = today. 0=Mon, 1=Tue, 2=Wed, 3=Thu, 4=Fri

// Wire mobile buttons to existing desktop functionality
document.getElementById('mobile-config-btn')?.addEventListener('click', () => openModal());
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
    // Find this week's Monday
    const monday = new Date(today);
    const offset = todayDow === 0 ? -6 : 1 - todayDow;
    monday.setDate(today.getDate() + offset);

    const dayNames = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri'];

    for (let i = 0; i < 5; i++) {
        const d = new Date(monday);
        d.setDate(monday.getDate() + i);
        const isToday = d.toDateString() === today.toDateString();
        // mobileSelectedDay: null=today, 0=Mon...4=Fri (matches timetable indices)
        const isActive = mobileSelectedDay === null ? isToday : (mobileSelectedDay === i);

        const el = document.createElement('div');
        el.className = 'mwd' + (isActive ? ' active' : '');
        el.innerHTML = `<span class="mwd-label">${dayNames[i]}</span><span class="mwd-num">${d.getDate()}</span>`;
        const dayIndex = i;
        el.addEventListener('click', () => {
            mobileSelectedDay = dayIndex;
            const timeline = document.getElementById('mobile-timeline');
            if (timeline) {
                timeline.style.transition = 'opacity 0.12s ease-out';
                timeline.style.opacity = '0';
                setTimeout(() => {
                    buildMobileWeekStrip();
                    updateMobileDateText(dayIndex);
                    if (lastTimetableData) renderMobileView(lastTimetableData);
                    timeline.style.opacity = '1';
                }, 120);
            } else {
                buildMobileWeekStrip();
                updateMobileDateText(dayIndex);
                if (lastTimetableData) renderMobileView(lastTimetableData);
            }
        });
        strip.appendChild(el);
    }
}

// === Issue #11: Dynamic header date ===
function updateMobileDateText(selectedIdx) {
    const el = document.getElementById('mobile-date-text');
    if (!el) return;

    const today = new Date();

    if (selectedIdx === undefined || selectedIdx === null) {
        // Show today's date
        const todayDow = today.getDay();
        const isWeekend = todayDow === 0 || todayDow === 6;
        if (isWeekend || mobileSelectedDay === null) {
            el.textContent = today.toLocaleDateString('en-US', { weekday: 'long', month: 'short', day: 'numeric' });
        }
        return;
    }

    // Calculate date for the selected weekday
    const todayDow = today.getDay();
    const monday = new Date(today);
    const offset = todayDow === 0 ? -6 : 1 - todayDow;
    monday.setDate(today.getDate() + offset);
    const selectedDate = new Date(monday);
    selectedDate.setDate(monday.getDate() + selectedIdx);

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
    // Map today to timetable index (Mon=0...Fri=4), weekend defaults to 0 (Mon)
    const todayTtIdx = (todayDow >= 1 && todayDow <= 5) ? todayDow - 1 : 0;
    const currentDay = mobileSelectedDay === null ? todayTtIdx : mobileSelectedDay;

    if (deltaX < -60 && currentDay < 4) {
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
        timeline.style.transition = 'opacity 0.12s ease-out';
        timeline.style.opacity = '0';
        setTimeout(() => {
            buildMobileWeekStrip();
            updateMobileDateText(mobileSelectedDay);
            if (lastTimetableData) renderMobileView(lastTimetableData);
            timeline.style.opacity = '1';
        }, 120);
    } else {
        buildMobileWeekStrip();
        updateMobileDateText(mobileSelectedDay);
        if (lastTimetableData) renderMobileView(lastTimetableData);
    }
}, { passive: true });

// === Issue #12: Contextual empty states ===
function getNextClassInfo(timetableData, fromDayIdx) {
    if (!timetableData) return null;
    const dayNames = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday'];
    // Search from the next day onwards, wrapping around
    for (let offset = 1; offset <= 5; offset++) {
        const checkIdx = (fromDayIdx + offset) % 5;
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
    // Map today to timetable index: Mon=0...Fri=4, weekend=-1
    const todayTtIdx = (todayDow >= 1 && todayDow <= 5) ? todayDow - 1 : -1;
    // mobileSelectedDay is already 0=Mon...4=Fri or null (=today)
    const ttIdx = mobileSelectedDay === null ? todayTtIdx : mobileSelectedDay;

    // Clear previous content but keep empty state element
    timeline.querySelectorAll('.m-past, .m-now-divider, .m-hero-wrap, .m-up-wrap, .m-later').forEach(el => el.remove());

    if (ttIdx === -1 || !timetableData[ttIdx] || timetableData[ttIdx].length === 0) {
        timeline.classList.add('is-empty');
        emptyState.style.display = 'block';

        // Issue #12: Contextual empty state
        const isWeekend = ttIdx === -1;
        const nextInfo = getNextClassInfo(timetableData, isWeekend ? 4 : ttIdx);

        if (isWeekend) {
            emptyState.querySelector('h2').textContent = 'Enjoy your weekend!';
            emptyState.querySelector('p').textContent = nextInfo
                ? `Monday: ${nextInfo.subject} at ${nextInfo.time}`
                : 'No upcoming classes found.';
        } else {
            const dayNames = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday'];
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
            <div class="m-later-loc">${cls.location}</div>
        `;
        timeline.appendChild(el);
    });
}

// Init mobile UI
buildMobileWeekStrip();
updateMobileDateText();

// Refresh mobile view every minute to keep current/upcoming accurate
setInterval(() => {
    if (lastTimetableData) renderMobileView(lastTimetableData);
    updateMobileDateText();
}, 60000);



