# UI Architecture & Specification Document
**Feature: Zero-Bloat HCI Side Menu & Dedicated "Find Free Rooms" Workspace**
**Branch:** `feature/side-menu-and-free-rooms`  
**Application:** FAST NUCES Timetable Generator & Schedule Builder

---

## 1. Design Philosophy & Core Principles

This UI feature extension was designed with **Applied Human-Computer Interaction (HCI)** principles and strict zero-bloat performance constraints:

1. **Native Speed & Zero External Dependencies:**
   - Uses native system fonts (`system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, ...`).
   - Zero custom web font downloads to preserve sub-second initial paint and instant interaction times.
2. **Pure Reuse of Design System:**
   - 100% compliant with existing CSS variables (`--bg-color`, `--surface-color`, `--surface-hover`, `--border-color`, `--text-primary`, `--text-secondary`, `--text-tertiary`, `--accent`, `--accent-subtle`, `--r-sm`, `--r-md`, `--r-lg`, `--r-full`).
3. **Fitts's Law ($T = a + b \log_2(2D/W)$):**
   - Eliminated nested cards and tiny chips inside the side menu.
   - Replaced with full-width horizontal navigation list bars ($\ge 48\text{px}$ touch target height) that make tapping effortless on both mobile screens and desktops.
4. **Hick's Law & Progressive Disclosure:**
   - Side menu serves as a clean 1-click launchpad.
   - Complex multi-parameter interactions (like finding free rooms) progressively disclose inside a focused, dedicated modal workspace (`#rooms-modal`).

---

## 2. Button Placements & Navigation Triggers

### Desktop PC View
* **Location:** Top navigation header (`.app-header` $\rightarrow$ `.header-controls`).
* **Trigger Element:** `#menu-toggle-btn` (icon button with hamburger SVG `☰`).
* **Placement Order:** Live Clock Indicator $\rightarrow$ Theme Switcher (`#theme-toggle`) $\rightarrow$ **Menu Button (`#menu-toggle-btn`)** $\rightarrow$ Configure Button (`#open-config-btn`).
* **Keyboard Shortcut:** Press <kbd>M</kbd> to toggle the menu open/closed.

### Mobile Phone View
* **Location:** Top sticky mobile header (`.mobile-header` $\rightarrow$ `.mobile-header-btns`).
* **Trigger Element:** `#mobile-menu-btn` (circular icon button with hamburger SVG `☰`).
* **UX Refinement:** Replaced the redundant top configure sliders icon with `#mobile-menu-btn`, as the primary *Configure* tab is permanently accessible in the bottom sticky navigation bar (`.mobile-nav`).

---

## 3. Side Drawer Architecture (`#drawer-overlay` & `#side-drawer`)

### Visual Structure
* **Overlay Scrim:** Fixed viewport backdrop (`rgba(0, 0, 0, 0.45)` with `backdrop-filter: blur(4px)`).
* **Drawer Panel:** Fixed right sheet docked at `width: 320px` (or `85vw` on mobile) with gentle cubic-bezier slide-in transition (`0.3s cubic-bezier(0.16, 1, 0.3, 1)`).
* **Header:** Clean `<h2>Menu</h2>` with close button (`#close-drawer-btn`).

### Linear Navigation Rows (`.drawer-nav-list`)
The side menu contains 4 linear, high-affordance navigation bars:

| Element ID | Action / Destination | Visual Elements |
| :--- | :--- | :--- |
| `#nav-item-export` | **Export as PNG** | Download icon + "Export as PNG" + Trailing Chevron `›` |
| `#nav-item-rooms` | **Find Free Rooms** | Campus Building icon + "Find Free Rooms" + Trailing Chevron `›` |
| `#nav-item-config` | **Configure Schedule** | Sliders icon + "Configure Schedule" + Trailing Chevron `›` |
| `#nav-item-theme` | **Appearance (Theme)** | Theme icon + "Appearance" + Badge (`Dark` / `Light`) |

### Accessibility & Micro-Gestures
- **Focus Trap:** Tabbing stays trapped strictly inside the open drawer.
- **Escape Key:** Pressing <kbd>Esc</kbd> closes the active drawer and restores focus.
- **Swipe-to-Dismiss:** Swiping right ($\ge 75\text{px}$) on mobile screens smoothly dismisses the drawer.

---

## 4. Dedicated "Find Free Rooms" Workspace (`#rooms-modal`)

When `#nav-item-rooms` is clicked, the side drawer smoothly closes and the dedicated Free Rooms modal (`#rooms-modal`) opens.

### Workspace Controls
1. **University Block Selector (`.segmented-grid-4`):**
   - 4 discrete segmented radio buttons: **`Block A`**, **`Block B`**, **`Block C`**, **`Block D`** (`data-block="A|B|C|D"`).
2. **Day Selector (`.segmented-grid-5`):**
   - 5 weekday buttons: `Mon`, `Tue`, `Wed`, `Thu`, `Fri` (`data-day="Monday|Tuesday|..."`).
   - **Smart Default:** Automatically selects today's weekday on initialization (defaults to Monday on weekends).
3. **Time Slot Selector (`#time-slot-select`):**
   - Clean native stylized select dropdown with standard FAST Islamabad 80-minute time slots:
     - `08:30 - 09:50` (Slot 1: 08:30 AM – 09:50 AM)
     - `10:00 - 11:20` (Slot 2: 10:00 AM – 11:20 AM)
     - `11:30 - 12:50` (Slot 3: 11:30 AM – 12:50 PM)
     - `01:00 - 02:20` (Slot 4: 01:00 PM – 02:20 PM)
     - `02:30 - 03:50` (Slot 5: 02:30 PM – 03:50 PM)
     - `03:55 - 05:15` (Slot 6: 03:55 PM – 05:15 PM)
   - **Smart Default:** Automatically pre-selects the ongoing or next upcoming slot based on client device clock time.
4. **Primary Action Button (`#find-rooms-btn`):**
   - Scans and triggers room vacancy calculation.
5. **Results Grid (`#rooms-results-container` & `#rooms-grid`):**
   - Displays available room chips (e.g., `A-101`, `A-102`, `C-402`, `D-506`) styled with `--surface-color` and active hover lifts.

---

## 5. File Inventory & DOM Element Cross-Reference

| File | Key Changes |
| :--- | :--- |
| `frontend/index.html` | Added `#menu-toggle-btn` (desktop header), replaced top config with `#mobile-menu-btn` (mobile header), added `#drawer-overlay` with `.drawer-nav-list`, added `#rooms-modal`. |
| `frontend/style.css` | Appended `.drawer-overlay`, `.side-drawer`, `.drawer-nav-item`, `.segmented-grid`, `.form-select`, `.rooms-results-container`, `.room-chip`. |
| `frontend/script.js` | Added drawer lifecycle (`openDrawer`, `closeDrawer`), rooms modal lifecycle (`openRoomsModal`, `closeRoomsModal`, `initRoomDefaults`, `renderFreeRoomResults`), and <kbd>M</kbd>/<kbd>Esc</kbd> keyboard handlers. |
