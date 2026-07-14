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
});

function updateThemeIcon(theme) {
    sunIcon.style.display = theme === 'dark' ? 'block' : 'none';
    moonIcon.style.display = theme === 'light' ? 'block' : 'none';
}

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

openBtn.addEventListener('click', () => modal.classList.add('active'));
closeBtn.addEventListener('click', () => modal.classList.remove('active'));

// Close on overlay click
modal.addEventListener('click', (e) => {
    if (e.target === modal) modal.classList.remove('active');
});

// Close on Escape
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && modal.classList.contains('active')) {
        modal.classList.remove('active');
    }
});

// === Keyboard Shortcuts ===
document.addEventListener('keydown', (e) => {
    // Don't fire shortcuts when typing in inputs
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'SELECT' || e.target.tagName === 'TEXTAREA') return;
    
    if (e.key === 'c' || e.key === 'C') {
        modal.classList.add('active');
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
        } else {
            console.error('Failed to load subjects:', data.message);
        }
    } catch (e) {
        console.error('Error fetching subjects:', e);
        document.getElementById('subject-list').innerHTML = 
            '<div style="padding:20px;text-align:center;color:var(--text-secondary);font-size:0.85rem;">Could not connect to the server.<br>Is <code>app.py</code> running?</div>';
    }
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

            renderTimetable(data.timetable);
            renderMobileView(data.timetable);
            updateStatusBar(batch, course, section, selectedSubjects, selectedNames);
            
            // Update configure button
            openBtn.innerHTML = `${gearSvg} ${batch}-${course}-${section}`;
            
            // Show grid, hide empty state
            document.getElementById('empty-state').style.display = 'none';
            document.getElementById('week-grid').style.display = 'grid';
            
            modal.classList.remove('active');
        } else {
            alert('Error: ' + data.message);
        }
    } catch (error) {
        alert('Failed to connect to API. Is app.py running?');
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
        col.innerHTML = `<div class="day-header">${days[idx]}</div>`;
        
        if (daySchedule.length === 0) {
            // Empty day placeholder
            const emptyMsg = document.createElement('div');
            emptyMsg.style.cssText = 'display:flex;align-items:center;justify-content:center;height:120px;color:var(--text-tertiary);font-size:0.75rem;font-weight:400;';
            emptyMsg.textContent = 'No classes';
            col.appendChild(emptyMsg);
        }
        
        daySchedule.forEach(cls => {
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
            card.style.setProperty('--start', startVal);
            card.style.setProperty('--duration', duration);
            card.style.setProperty('--card-bg', subjectColors[cls.subject].bg);
            card.style.setProperty('--card-border', subjectColors[cls.subject].border);
            
            card.innerHTML = `
                <h3>${cls.subject}</h3>
                <p class="card-time">${cls.start_time} – ${cls.end_time}</p>
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
let mobileSelectedDay = null; // null = today

// Wire mobile buttons to existing desktop functionality
document.getElementById('mobile-config-btn')?.addEventListener('click', () => modal.classList.add('active'));
document.getElementById('mobile-settings-btn')?.addEventListener('click', () => modal.classList.add('active'));

// Mobile theme toggle syncs with desktop toggle
document.getElementById('mobile-theme-toggle')?.addEventListener('click', () => {
    themeToggleBtn.click(); // reuse desktop toggle
    // Sync mobile icons
    const theme = html.getAttribute('data-theme');
    document.querySelector('.m-sun').style.display = theme === 'dark' ? 'block' : 'none';
    document.querySelector('.m-moon').style.display = theme === 'light' ? 'block' : 'none';
});

// Build the week strip
function buildMobileWeekStrip() {
    const strip = document.getElementById('mobile-week-strip');
    if (!strip) return;
    strip.innerHTML = '';

    const today = new Date();
    const dayOfWeek = today.getDay(); // 0=Sun
    const startOfWeek = new Date(today);
    startOfWeek.setDate(today.getDate() - dayOfWeek); // Sunday

    const dayNames = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];

    for (let i = 0; i < 7; i++) {
        const d = new Date(startOfWeek);
        d.setDate(startOfWeek.getDate() + i);
        const isToday = d.toDateString() === today.toDateString();
        const isActive = mobileSelectedDay === null ? isToday : (mobileSelectedDay === i);

        const el = document.createElement('div');
        el.className = 'mwd' + (isActive ? ' active' : '');
        el.innerHTML = `<span class="mwd-label">${dayNames[i]}</span><span class="mwd-num">${d.getDate()}</span>`;
        el.addEventListener('click', () => {
            mobileSelectedDay = i;
            buildMobileWeekStrip();
            if (lastTimetableData) renderMobileView(lastTimetableData);
        });
        strip.appendChild(el);
    }
}

// Update header date text
function updateMobileDateText() {
    const el = document.getElementById('mobile-date-text');
    if (!el) return;
    const now = new Date();
    const opts = { weekday: 'long', month: 'short', day: 'numeric' };
    el.textContent = now.toLocaleDateString('en-US', opts);
}

// Map day index (0=Sun...6=Sat) to timetable array index (0=Mon...4=Fri)
function dayIndexToTimetableIndex(dayIdx) {
    // dayIdx: 0=Sun, 1=Mon, 2=Tue, 3=Wed, 4=Thu, 5=Fri, 6=Sat
    // timetable: 0=Mon, 1=Tue, 2=Wed, 3=Thu, 4=Fri
    if (dayIdx >= 1 && dayIdx <= 5) return dayIdx - 1;
    return -1; // Weekend
}

// Format time for display
function formatTimeLabel(timeStr) {
    const parts = timeStr.split(':');
    let h = parseInt(parts[0], 10);
    const m = parts[1] || '00';
    if (h >= 1 && h <= 7) h += 12;
    const ampm = h >= 12 ? 'PM' : 'AM';
    const h12 = h > 12 ? h - 12 : (h === 0 ? 12 : h);
    return m === '00' ? `${h12} ${ampm}` : `${h12}:${m}`;
}

// Get current time as decimal hours
function getCurrentDecimalTime() {
    const now = new Date();
    return now.getHours() + now.getMinutes() / 60;
}

// Render the mobile agenda view for the selected day
function renderMobileView(timetableData) {
    lastTimetableData = timetableData;
    const timeline = document.getElementById('mobile-timeline');
    const emptyState = document.getElementById('mobile-empty-state');
    if (!timeline) return;

    // Determine which day to show
    const today = new Date();
    const selectedDayIdx = mobileSelectedDay === null ? today.getDay() : mobileSelectedDay;
    const ttIdx = dayIndexToTimetableIndex(selectedDayIdx);

    // Clear previous content but keep empty state element
    timeline.querySelectorAll('.m-past, .m-now-divider, .m-hero-wrap, .m-up-wrap, .m-later').forEach(el => el.remove());

    if (ttIdx === -1 || !timetableData[ttIdx] || timetableData[ttIdx].length === 0) {
        emptyState.style.display = 'block';
        emptyState.querySelector('h2').textContent = 'No classes';
        emptyState.querySelector('p').textContent = ttIdx === -1 ? 'Enjoy your weekend!' : 'No classes scheduled for this day.';
        return;
    }

    emptyState.style.display = 'none';
    const classes = [...timetableData[ttIdx]].sort((a, b) => parseTime(a.start_time) - parseTime(b.start_time));
    const nowDecimal = getCurrentDecimalTime();
    const isViewingToday = (mobileSelectedDay === null || mobileSelectedDay === today.getDay());

    // Categorize classes
    const past = [];
    let current = null;
    let upcoming = null;
    const later = [];

    classes.forEach(cls => {
        const start = parseTime(cls.start_time);
        const end = parseTime(cls.end_time);

        if (!isViewingToday) {
            // When viewing another day, everything is "later" (no past/current logic)
            later.push(cls);
        } else if (end <= nowDecimal) {
            past.push(cls);
        } else if (start <= nowDecimal && end > nowDecimal) {
            current = cls;
        } else if (!current && !upcoming && start > nowDecimal) {
            // If nothing is current, the first future class is "upcoming"
            upcoming = cls;
        } else if (upcoming && start > nowDecimal) {
            later.push(cls);
        } else if (!upcoming) {
            upcoming = cls;
        } else {
            later.push(cls);
        }
    });

    // If no current class but we have an upcoming, promote first upcoming
    if (!current && !upcoming && later.length > 0) {
        upcoming = later.shift();
    }

    const checkSvg = '<svg viewBox="0 0 24 24"><polyline points="20 6 9 17 4 12"/></svg>';
    const capSvg = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 10v6M2 10l10-5 10 5-10 5z"/><path d="M6 12v5c0 1.5 2.7 3 6 3s6-1.5 6-3v-5"/></svg>';

    // Render PAST
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
            <div class="m-past-time">${cls.start_time} – ${cls.end_time}</div>
        `;
        timeline.appendChild(el);
    });

    // Render NOW divider (only if viewing today and there are past classes or a current class)
    if (isViewingToday && (past.length > 0 || current)) {
        const nowDiv = document.createElement('div');
        nowDiv.className = 'm-now-divider';
        const h = today.getHours();
        const m = today.getMinutes().toString().padStart(2, '0');
        const ampm = h >= 12 ? 'PM' : 'AM';
        const h12 = h > 12 ? h - 12 : (h === 0 ? 12 : h);
        nowDiv.innerHTML = `<span class="m-now-label">Now · ${h12}:${m} ${ampm}</span>`;
        timeline.appendChild(nowDiv);
    }

    // Render CURRENT (Hero Card)
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
                    <span>${current.start_time}</span>
                    <span>${current.end_time}</span>
                </div>
                <div class="m-hero-loc">Location: <strong>${current.location}</strong></div>
                <div class="m-prog-track"><div class="m-prog-fill" style="width:${progress}%"></div></div>
            </div>
        `;
        timeline.appendChild(el);
    }

    // Render UPCOMING (Clean Card)
    if (upcoming) {
        const el = document.createElement('div');
        el.className = 'm-up-wrap';
        el.innerHTML = `
            <span class="mtl-label">${formatTimeLabel(upcoming.start_time)}</span>
            <span class="mtl-dot"></span>
            <div class="m-up-card">
                <div class="m-up-badge">Upcoming</div>
                <div class="m-up-time">${upcoming.start_time} – ${upcoming.end_time}</div>
                <div class="m-up-subject">${upcoming.subject}</div>
                <div class="m-up-detail">${upcoming.location}</div>
            </div>
        `;
        timeline.appendChild(el);
    }

    // Render LATER (Text only)
    later.forEach(cls => {
        const el = document.createElement('div');
        el.className = 'm-later';
        el.innerHTML = `
            <span class="mtl-label">${formatTimeLabel(cls.start_time)}</span>
            <span class="mtl-dot"></span>
            <div class="m-later-time">${cls.start_time} – ${cls.end_time}</div>
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
}, 60000);
