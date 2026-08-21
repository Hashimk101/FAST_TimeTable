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

// === Side Drawer Menu & Free Rooms Controller ===
const drawerOverlay = document.getElementById('drawer-overlay');
const sideDrawer = document.getElementById('side-drawer');
const openDrawerDesktopBtn = document.getElementById('menu-toggle-btn');
const openDrawerMobileBtn = document.getElementById('mobile-menu-btn');
const closeDrawerBtn = document.getElementById('close-drawer-btn');

const navItemExport = document.getElementById('nav-item-export');
const navItemRooms = document.getElementById('nav-item-rooms');
const navItemConfig = document.getElementById('nav-item-config');
const navItemTheme = document.getElementById('nav-item-theme');
const navThemeStatus = document.getElementById('nav-theme-status');

const roomsModal = document.getElementById('rooms-modal');
const closeRoomsModalBtn = document.getElementById('close-rooms-modal-btn');
const findRoomsBtn = document.getElementById('find-rooms-btn');
const timeSlotSelect = document.getElementById('time-slot-select');
const blockSegmentBtns = document.querySelectorAll('#rooms-modal [data-block]');
const daySegmentBtns = document.querySelectorAll('#rooms-modal [data-day]');
const roomsResultsContainer = document.getElementById('rooms-results-container');
const roomsGrid = document.getElementById('rooms-grid');
const resultsCountBadge = document.getElementById('results-count-badge');
const resultsContextLabel = document.getElementById('results-context-label');

let drawerLastFocused = null;
let selectedRoomBlock = 'C';
let selectedRoomDay = 'Monday';

function openDrawer() {
    drawerLastFocused = document.activeElement;
    drawerOverlay?.classList.add('active');
    drawerOverlay?.setAttribute('aria-hidden', 'false');
    const firstFocusable = sideDrawer?.querySelector('button, [tabindex]:not([tabindex="-1"])');
    if (firstFocusable) firstFocusable.focus({ preventScroll: true });
}

function closeDrawer() {
    drawerOverlay?.classList.remove('active');
    drawerOverlay?.setAttribute('aria-hidden', 'true');
    if (drawerLastFocused) drawerLastFocused.focus();
}

openDrawerDesktopBtn?.addEventListener('click', openDrawer);
openDrawerMobileBtn?.addEventListener('click', openDrawer);
closeDrawerBtn?.addEventListener('click', closeDrawer);

// Close drawer on overlay click
drawerOverlay?.addEventListener('click', (e) => {
    if (e.target === drawerOverlay) closeDrawer();
});

// Mobile touch swipe to dismiss drawer
let drawerTouchStartX = 0;
sideDrawer?.addEventListener('touchstart', (e) => {
    drawerTouchStartX = e.touches[0].clientX;
}, { passive: true });

sideDrawer?.addEventListener('touchend', (e) => {
    const deltaX = e.changedTouches[0].clientX - drawerTouchStartX;
    if (deltaX > 75) closeDrawer();
});

// Drawer focus trap
drawerOverlay?.addEventListener('keydown', (e) => {
    if (e.key !== 'Tab') return;
    const focusables = sideDrawer?.querySelectorAll('button, input, select, [tabindex]:not([tabindex="-1"])') || [];
    if (focusables.length === 0) return;
    const first = focusables[0];
    const last = focusables[focusables.length - 1];
    if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
    } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
    }
});

// --- Menu Navigation Actions ---
navItemExport?.addEventListener('click', () => {
    closeDrawer();
    generateTimetablePNG();
});

navItemRooms?.addEventListener('click', () => {
    openRoomsModal();
});

navItemConfig?.addEventListener('click', () => {
    closeDrawer();
    openModal();
});

function syncNavThemeStatus() {
    const theme = html.getAttribute('data-theme') || 'dark';
    if (navThemeStatus) navThemeStatus.textContent = theme === 'dark' ? 'Dark' : 'Light';
}

navItemTheme?.addEventListener('click', () => {
    themeToggleBtn?.click();
    syncNavThemeStatus();
});

// --- Free Rooms Modal Logic ---
function openRoomsModal() {
    closeDrawer();
    initRoomDefaults();
    roomsModal?.classList.add('active');
    const firstFocusable = roomsModal?.querySelector('button, select, input');
    if (firstFocusable) firstFocusable.focus({ preventScroll: true });
}

function closeRoomsModal() {
    roomsModal?.classList.remove('active');
}

closeRoomsModalBtn?.addEventListener('click', closeRoomsModal);
roomsModal?.addEventListener('click', (e) => {
    if (e.target === roomsModal) closeRoomsModal();
});

function initRoomDefaults() {
    const days = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
    const currentDay = days[new Date().getDay()];
    selectedRoomDay = (currentDay === 'Sunday' || currentDay === 'Saturday') ? 'Monday' : currentDay;
    
    daySegmentBtns.forEach(btn => {
        const isActive = btn.dataset.day === selectedRoomDay;
        btn.classList.toggle('active', isActive);
        btn.setAttribute('aria-checked', isActive ? 'true' : 'false');
    });

    const now = new Date();
    const currentMins = now.getHours() * 60 + now.getMinutes();
    const slots = [
        { label: '08:30 - 09:50', end: 9 * 60 + 50 },
        { label: '10:00 - 11:20', end: 11 * 60 + 20 },
        { label: '11:30 - 12:50', end: 12 * 60 + 50 },
        { label: '01:00 - 02:20', end: 14 * 60 + 20 },
        { label: '02:30 - 03:50', end: 15 * 60 + 50 },
        { label: '03:55 - 05:15', end: 17 * 60 + 15 },
    ];
    const matchedSlot = slots.find(s => currentMins <= s.end);
    if (matchedSlot && timeSlotSelect) {
        timeSlotSelect.value = matchedSlot.label;
    }
}

blockSegmentBtns.forEach(btn => {
    btn.addEventListener('click', () => {
        blockSegmentBtns.forEach(b => {
            b.classList.remove('active');
            b.setAttribute('aria-checked', 'false');
        });
        btn.classList.add('active');
        btn.setAttribute('aria-checked', 'true');
        selectedRoomBlock = btn.dataset.block || 'A';
    });
});

daySegmentBtns.forEach(btn => {
    btn.addEventListener('click', () => {
        daySegmentBtns.forEach(b => {
            b.classList.remove('active');
            b.setAttribute('aria-checked', 'false');
        });
        btn.classList.add('active');
        btn.setAttribute('aria-checked', 'true');
        selectedRoomDay = btn.dataset.day || 'Monday';
    });
});

let cachedRoomsData = null;

findRoomsBtn?.addEventListener('click', async () => {
    const timeSlot = timeSlotSelect?.value || '08:30 - 09:50';
    const [startStr, endStr] = timeSlot.split(' - ');
    const slotStart = parseTime(startStr);
    const slotEnd = parseTime(endStr);
    
    // Fetch data if not cached
    if (!cachedRoomsData) {
        findRoomsBtn.innerHTML = 'Scanning...';
        findRoomsBtn.disabled = true;
        let data = await fetchDecoded('data/rooms.bin');
        if (!data) data = await fetchDecoded('/data/rooms.bin');
        cachedRoomsData = data;
        findRoomsBtn.innerHTML = 'Find Rooms';
        findRoomsBtn.disabled = false;
    }
    
    if (!cachedRoomsData) {
        showToast('Failed to load room data.', 'error');
        return;
    }
    
    const allRooms = cachedRoomsData.rooms;
    const occupiedData = cachedRoomsData.occupied;
    
    // Filter rooms by selected block (C or D)
    const blockRooms = allRooms.filter(r => r.startsWith(selectedRoomBlock + '-'));
    const freeRooms = [];
    
    const dayOccupancy = occupiedData[selectedRoomDay] || {};
    
    for (const room of blockRooms) {
        const classes = dayOccupancy[room] || [];
        let isOccupied = false;
        
        for (const cls of classes) {
            const clsStart = parseTime(cls.s);
            const clsEnd = parseTime(cls.e);
            
            // Overlap condition: max(start1, start2) < min(end1, end2)
            if (Math.max(slotStart, clsStart) < Math.min(slotEnd, clsEnd)) {
                isOccupied = true;
                break;
            }
        }
        
        if (!isOccupied) {
            freeRooms.push(room);
        }
    }

    renderFreeRoomResults(freeRooms, selectedRoomBlock, selectedRoomDay, timeSlot);
});

function renderFreeRoomResults(rooms, block, day, slot) {
    if (!roomsResultsContainer || !roomsGrid) return;
    roomsResultsContainer.style.display = 'block';
    resultsCountBadge.textContent = `${rooms.length} Free Rooms`;
    resultsContextLabel.textContent = `Block ${block} · ${day.slice(0, 3)} · ${slot}`;

    if (rooms.length === 0) {
        roomsGrid.innerHTML = `<div class="rooms-empty">No free rooms found for this slot.</div>`;
        return;
    }

    roomsGrid.innerHTML = rooms
        .map(room => `<div class="room-chip">${room}</div>`)
        .join('');
}

// === Global Keyboard Shortcuts ===
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
        if (drawerOverlay?.classList.contains('active')) {
            closeDrawer();
            return;
        }
        if (roomsModal?.classList.contains('active')) {
            closeRoomsModal();
            return;
        }
        if (modal?.classList.contains('active')) {
            closeModal();
            return;
        }
    }

    // Don't fire shortcuts when typing in inputs
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'SELECT' || e.target.tagName === 'TEXTAREA') return;
    // Don't hijack Ctrl/Cmd shortcuts (Ctrl+C = copy, etc.)
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    
    if (e.key === 'c' || e.key === 'C') {
        openModal();
    }
    if (e.key === 'm' || e.key === 'M') {
        if (drawerOverlay?.classList.contains('active')) {
            closeDrawer();
        } else {
            openDrawer();
        }
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
        const res = await fetch(url + queryParam);
        if (!res.ok) return null;
        const text = await res.text();
        return decodeData(text);
    } catch (e) {
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


// === Generate Timetable ===
const form = document.getElementById('config-form');
const gearSvg = `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><line x1="4" y1="21" x2="4" y2="14"></line><line x1="4" y1="10" x2="4" y2="3"></line><line x1="12" y1="21" x2="12" y2="12"></line><line x1="12" y1="8" x2="12" y2="3"></line><line x1="20" y1="21" x2="20" y2="16"></line><line x1="20" y1="12" x2="20" y2="3"></line><line x1="1" y1="14" x2="7" y2="14"></line><line x1="9" y1="8" x2="15" y2="8"></line><line x1="17" y1="16" x2="23" y2="16"></line></svg>`;

let lastConfig = null;

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
        const res = await fetch(`/data/version.json?t=${now}`, { cache: 'no-cache' });
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
            fetch(`/data/version.json?t=${Date.now()}`, { cache: 'no-cache' })
                .then(r => r.ok ? r.json() : null)
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





// ===================================================================
// HIGH-RES PNG EXPORTER (Clarity Focused)
// ===================================================================
async function generateTimetablePNG() {
    if (!lastConfig) {
        showToast('Please configure a schedule first.');
        return;
    }
    const cachedTtStr = localStorage.getItem('cachedTimetable');
    if (!cachedTtStr) return;
    const timetable = JSON.parse(cachedTtStr);
    
    // Scale factor for high resolution (e.g. 2x for 4K-ish clarity)
    const scale = 3; 
    const w = 1920 * scale;
    const h = 1080 * scale;
    
    const canvas = document.createElement('canvas');
    canvas.width = w;
    canvas.height = h;
    const ctx = canvas.getContext('2d', { alpha: false });
    
    // Clarity colors (Clean light mode, high contrast)
    const bg = '#ffffff';
    const textDark = '#1a1a1a';
    const textLight = '#555555';
    const border = '#e2e8f0';
    const headerBg = '#0f172a'; // Dark slate for branding header
    const headerText = '#ffffff';
    
    // Fill Background
    ctx.fillStyle = bg;
    ctx.fillRect(0, 0, w, h);
    
    // 1. Draw Branding Header
    const headerHeight = 120 * scale;
    ctx.fillStyle = headerBg;
    ctx.fillRect(0, 0, w, headerHeight);
    
    // Header Text
    ctx.fillStyle = headerText;
    ctx.font = \old \px system-ui, -apple-system, sans-serif\;
    ctx.textAlign = 'left';
    ctx.textBaseline = 'middle';
    ctx.fillText('FAST NUCES ISLAMABAD', 40 * scale, headerHeight / 2);
    
    // Batch/Section Badge
    ctx.textAlign = 'right';
    const batchText = \ \ - \;
    ctx.fillText(batchText, w - 40 * scale, headerHeight / 2);
    
    // 2. Setup Grid Dimensions
    const padX = 40 * scale;
    const padY = 40 * scale;
    const topOffset = headerHeight + padY;
    const gridW = w - (padX * 2);
    const gridH = h - topOffset - padY;
    
    const days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
    const cols = 6;
    const colW = gridW / cols;
    
    // Time bounds (08:00 to 17:30 approx = 8.0 to 17.5 = 9.5 hours duration)
    // We'll dynamically find min and max time to scale vertically
    let minTime = 8.5; // 8:30 AM
    let maxTime = 17.25; // 5:15 PM
    
    // Adjust if classes fall outside
    timetable.forEach(day => {
        day.forEach(cls => {
            const s = parseTime(cls.start_time) / 60;
            const e = parseTime(cls.end_time) / 60;
            if (s > 0 && s < minTime) minTime = Math.floor(s);
            if (e > 0 && e > maxTime) maxTime = Math.ceil(e);
        });
    });
    
    const timeSpan = maxTime - minTime;
    const dayHeaderH = 50 * scale;
    const canvasBodyH = gridH - dayHeaderH;
    
    // 3. Draw Columns and Headers
    ctx.textAlign = 'center';
    for (let i = 0; i < cols; i++) {
        const cx = padX + i * colW;
        
        // Day Background Alternate
        if (i % 2 !== 0) {
            ctx.fillStyle = '#f8fafc';
            ctx.fillRect(cx, topOffset + dayHeaderH, colW, canvasBodyH);
        }
        
        // Column Divider
        if (i > 0) {
            ctx.strokeStyle = border;
            ctx.lineWidth = 2 * scale;
            ctx.beginPath();
            ctx.moveTo(cx, topOffset);
            ctx.lineTo(cx, topOffset + gridH);
            ctx.stroke();
        }
        
        // Day Header
        ctx.fillStyle = textDark;
        ctx.font = \old \px system-ui, sans-serif\;
        ctx.fillText(days[i], cx + colW/2, topOffset + dayHeaderH/2);
    }
    
    // Top border for grid body
    ctx.strokeStyle = border;
    ctx.lineWidth = 2 * scale;
    ctx.beginPath();
    ctx.moveTo(padX, topOffset + dayHeaderH);
    ctx.lineTo(padX + gridW, topOffset + dayHeaderH);
    ctx.stroke();
    
    // 4. Draw Class Cards
    const cardMarginX = 8 * scale;
    
    // Clarity Card Colors (High contrast pastels)
    const cardColors = [
        { bg: '#e0f2fe', border: '#7dd3fc', text: '#0369a1' },
        { bg: '#dcfce7', border: '#86efac', text: '#15803d' },
        { bg: '#f3e8ff', border: '#d8b4fe', text: '#6b21a8' },
        { bg: '#ffedd5', border: '#fdba74', text: '#c2410c' },
        { bg: '#fce7f3', border: '#f9a8d4', text: '#be185d' }
    ];
    
    timetable.forEach((daySchedule, dayIdx) => {
        const cx = padX + dayIdx * colW;
        
        daySchedule.forEach(cls => {
            const startHours = parseTime(cls.start_time) / 60;
            const endHours = parseTime(cls.end_time) / 60;
            if (startHours === 0 || endHours === 0) return;
            
            const startY = topOffset + dayHeaderH + ((startHours - minTime) / timeSpan) * canvasBodyH;
            const cardH = ((endHours - startHours) / timeSpan) * canvasBodyH;
            
            // Hash subject for color
            let hash = 0;
            for(let i=0; i<cls.subject.length; i++) hash = cls.subject.charCodeAt(i) + ((hash << 5) - hash);
            const colorIdx = Math.abs(hash) % cardColors.length;
            const colors = cardColors[colorIdx];
            
            const rectX = cx + cardMarginX;
            const rectY = startY;
            const rectW = colW - (cardMarginX * 2);
            
            // Draw Card Background
            ctx.fillStyle = colors.bg;
            ctx.beginPath();
            ctx.roundRect(rectX, rectY, rectW, cardH, 8 * scale);
            ctx.fill();
            ctx.strokeStyle = colors.border;
            ctx.lineWidth = 2 * scale;
            ctx.stroke();
            
            // Text constraints
            const maxTextW = rectW - (20 * scale);
            const textCx = rectX + rectW/2;
            
            // Draw Time
            ctx.fillStyle = colors.text;
            ctx.font = \px system-ui, sans-serif\;
            ctx.fillText(\ - \, textCx, rectY + 24 * scale);
            
            // Draw Subject
            ctx.font = \old \px system-ui, sans-serif\;
            const subjLines = wrapText(ctx, cls.subject, maxTextW);
            const totalTextH = subjLines.length * (24 * scale);
            let subjY = rectY + (cardH / 2) - (totalTextH / 2) + (10 * scale);
            
            subjLines.forEach(line => {
                ctx.fillText(line, textCx, subjY);
                subjY += 24 * scale;
            });
            
            // Draw Room
            ctx.font = \px system-ui, sans-serif\;
            ctx.fillText(cls.location, textCx, rectY + cardH - 16 * scale);
        });
    });
    
    // Export and download
    canvas.toBlob((blob) => {
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        const cleanName = \_\_\.replace(/[^a-zA-Z0-9]/g, '_');
        a.download = \FAST_Timetable_\.png\;
        a.click();
        URL.revokeObjectURL(url);
        showToast('Timetable exported as PNG successfully!', 'info');
    }, 'image/png', 1.0);
}

function wrapText(ctx, text, maxWidth) {
    const words = text.split(' ');
    const lines = [];
    let currentLine = words[0];

    for (let i = 1; i < words.length; i++) {
        const word = words[i];
        const width = ctx.measureText(currentLine + ' ' + word).width;
        if (width < maxWidth) {
            currentLine += ' ' + word;
        } else {
            lines.push(currentLine);
            currentLine = word;
        }
    }
    lines.push(currentLine);
    return lines;
}
