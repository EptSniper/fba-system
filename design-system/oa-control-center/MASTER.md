# Design System Master File

> **LOGIC:** When building a specific page, first check `design-system/pages/[page-name].md`.
> If that file exists, its rules **override** this Master file.
> If not, strictly follow the rules below.

---

**Project:** OA Control Center
**Generated:** 2026-06-27 13:20:22
**Category:** Smart Home/IoT Dashboard

---

## Global Rules

### Color Palette

> **Theme update 2026-06-29 (current):** the control center runs the **"Midnight Aurora"** premium
> dark theme — deep blue-black base, glass-layered surfaces, indigo→violet accent gradient, and a
> slow animated aurora backdrop. (It briefly trialed an "Analyst Light" theme earlier the same day;
> reverted to dark per operator preference.) Live values below mirror the implemented tokens in
> `control-center/app/globals.css` (the source of truth).

| Role | Hex / Value | CSS Variable |
|------|-------------|--------------|
| Accent (primary) | `#7C9DFF` | `--accent` (electric indigo) |
| Accent gradient | `linear-gradient(135deg,#6D8BFF,#9B6DFF)` | `--grad-accent` (buttons, brand, active nav) |
| Highlight | `#F5B544` | `--accent-2` (amber) |
| Background | `#070A12` | `--bg` (deep blue-black) |
| Surface | `#0E1320` + glass gradient | `--panel` |
| Inset surface | `#161D2E` | `--panel-2` |
| Text | `#EEF1F8` | `--text` |
| Muted text | `#9AA6BD` | `--text-muted` (~7:1) |
| Profit / Loss | `#34D39A` / `#FB6F84` | `--profit` / `--loss` |

**Color Notes:** Premium dark console. Glass cards (top-lit gradient + hairline border + inner
highlight + soft shadow) over an animated aurora (indigo/violet/amber radial wash + faint grid).
Indigo→violet gradient for primary actions, amber for highlights, emerald/rose for P&L.

### Typography

- **Heading Font:** Fira Code
- **Body Font:** Fira Sans
- **Mood:** dashboard, data, analytics, code, technical, precise
- **Google Fonts:** [Fira Code + Fira Sans](https://fonts.google.com/share?selection.family=Fira+Code:wght@400;500;600;700|Fira+Sans:wght@300;400;500;600;700)

**CSS Import:**
```css
@import url('https://fonts.googleapis.com/css2?family=Fira+Code:wght@400;500;600;700&family=Fira+Sans:wght@300;400;500;600;700&display=swap');
```

### Spacing Variables

| Token | Value | Usage |
|-------|-------|-------|
| `--space-xs` | `4px` / `0.25rem` | Tight gaps |
| `--space-sm` | `8px` / `0.5rem` | Icon gaps, inline spacing |
| `--space-md` | `16px` / `1rem` | Standard padding |
| `--space-lg` | `24px` / `1.5rem` | Section padding |
| `--space-xl` | `32px` / `2rem` | Large gaps |
| `--space-2xl` | `48px` / `3rem` | Section margins |
| `--space-3xl` | `64px` / `4rem` | Hero padding |

### Shadow Depths

| Level | Value | Usage |
|-------|-------|-------|
| `--shadow-sm` | `0 1px 2px rgba(0,0,0,0.05)` | Subtle lift |
| `--shadow-md` | `0 4px 6px rgba(0,0,0,0.1)` | Cards, buttons |
| `--shadow-lg` | `0 10px 15px rgba(0,0,0,0.1)` | Modals, dropdowns |
| `--shadow-xl` | `0 20px 25px rgba(0,0,0,0.15)` | Hero images, featured cards |

---

## Component Specs

### Buttons

```css
/* Primary Button */
.btn-primary {
  background: #22C55E;
  color: white;
  padding: 12px 24px;
  border-radius: 8px;
  font-weight: 600;
  transition: all 200ms ease;
  cursor: pointer;
}

.btn-primary:hover {
  opacity: 0.9;
  transform: translateY(-1px);
}

/* Secondary Button */
.btn-secondary {
  background: transparent;
  color: #0F172A;
  border: 2px solid #0F172A;
  padding: 12px 24px;
  border-radius: 8px;
  font-weight: 600;
  transition: all 200ms ease;
  cursor: pointer;
}
```

### Cards

```css
.card {
  background: #020617;
  border-radius: 12px;
  padding: 24px;
  box-shadow: var(--shadow-md);
  transition: all 200ms ease;
  cursor: pointer;
}

.card:hover {
  box-shadow: var(--shadow-lg);
  transform: translateY(-2px);
}
```

### Inputs

```css
.input {
  padding: 12px 16px;
  border: 1px solid #E2E8F0;
  border-radius: 8px;
  font-size: 16px;
  transition: border-color 200ms ease;
}

.input:focus {
  border-color: #0F172A;
  outline: none;
  box-shadow: 0 0 0 3px #0F172A20;
}
```

### Modals

```css
.modal-overlay {
  background: rgba(0, 0, 0, 0.5);
  backdrop-filter: blur(4px);
}

.modal {
  background: white;
  border-radius: 16px;
  padding: 32px;
  box-shadow: var(--shadow-xl);
  max-width: 500px;
  width: 90%;
}
```

---

## Style Guidelines

**Style:** Midnight Aurora (premium dark, data-dense + glassmorphism)

**Keywords:** Deep blue-black, glass cards, indigo→violet gradient, animated aurora backdrop, depth/layering, high contrast, command-console, KPI cards

**Best For:** Operator consoles, financial/analytics dashboards, premium SaaS, low-light/long-session use

**Key Effects:** Glass surfaces (gradient + hairline + inner highlight + soft shadow), animated aurora drift (18s), framer-motion page transitions + staggered reveals + hover lift, animated active-nav pill (layoutId), count-up figures, shimmer skeletons — all gated on `prefers-reduced-motion`

### Page Pattern

**Pattern Name:** Real-Time Monitoring

- **CTA Placement:** Above fold
- **Section Order:** Hero > Features > CTA

---

## Anti-Patterns (Do NOT Use)

- ❌ Slow updates
- ❌ No automation

### Additional Forbidden Patterns

- ❌ **Emojis as icons** — Use SVG icons (Heroicons, Lucide, Simple Icons)
- ❌ **Missing cursor:pointer** — All clickable elements must have cursor:pointer
- ❌ **Layout-shifting hovers** — Avoid scale transforms that shift layout
- ❌ **Low contrast text** — Maintain 4.5:1 minimum contrast ratio
- ❌ **Instant state changes** — Always use transitions (150-300ms)
- ❌ **Invisible focus states** — Focus states must be visible for a11y

---

## Pre-Delivery Checklist

Before delivering any UI code, verify:

- [ ] No emojis used as icons (use SVG instead)
- [ ] All icons from consistent icon set (Heroicons/Lucide)
- [ ] `cursor-pointer` on all clickable elements
- [ ] Hover states with smooth transitions (150-300ms)
- [ ] Light mode: text contrast 4.5:1 minimum
- [ ] Focus states visible for keyboard navigation
- [ ] `prefers-reduced-motion` respected
- [ ] Responsive: 375px, 768px, 1024px, 1440px
- [ ] No content hidden behind fixed navbars
- [ ] No horizontal scroll on mobile
