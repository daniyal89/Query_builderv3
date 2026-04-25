# UI & Visual Design Improvement Plan (Planning Only)

## Goal
Make the product feel professional, modern, and trustworthy for daily operational use.

## 1) Design Direction
- **Style:** clean enterprise dashboard, low visual noise, strong readability.
- **Tone:** confident, utility-first, not flashy.
- **Layout principle:** one clear primary action per screen; secondary actions visually de-emphasized.

## 2) Color System (Suggested)
- **Primary:** `#1D4ED8` (blue 700) for key CTAs and active states.
- **Primary hover:** `#1E40AF`.
- **Background:** `#F8FAFC` (very light slate).
- **Surface cards:** `#FFFFFF`.
- **Text primary:** `#0F172A`.
- **Text secondary:** `#475569`.
- **Border:** `#E2E8F0`.
- **Success:** `#16A34A`.
- **Warning:** `#D97706`.
- **Error:** `#DC2626`.
- **Info:** `#0284C7`.

## 3) Typography
- Use **Inter** (or system fallback).
- Base size: 14px or 15px for dense data UI.
- Heading scale:
  - H1: 28 / semibold
  - H2: 22 / semibold
  - H3: 18 / medium
- Use consistent line-height (1.4–1.6).

## 4) Spacing & Visual Rhythm
- 8px spacing system (`4, 8, 12, 16, 24, 32`).
- Card padding: 16–20px.
- Section gap: 24px.
- Keep form labels, controls, and helper text vertically aligned.

## 5) Navigation & Information Hierarchy
- Sidebar:
  - Group items under clear headings: Data, Querying, Operations.
  - Highlight active route with left accent bar + background tint.
- Header:
  - Persistent connection/engine badge.
  - Global search (future-ready), compact profile/help area.

## 6) Component Design Standards
- **Buttons:** consistent variants (Primary, Secondary, Ghost, Danger).
- **Inputs:** fixed heights, clear focus ring, inline validation message below field.
- **Tables:** sticky header, zebra row optional, hover state, dense/comfortable mode toggle.
- **Status badges:** standardized pill colors mapped to job states.
- **Empty states:** include icon + one-line guidance + CTA.

## 7) Page-Level UX Refinements
- Query Builder:
  - Split builder panel and SQL/results panel.
  - Add visual “query summary” chip row.
- Merge & Enrich:
  - Strong stepper UI (Upload → Resolve → Merge → Export).
  - Keep “next action” always visible.
- FTP/Drive pages:
  - Unified job card with progress, counters, elapsed time, and stop action.

## 8) Accessibility & Usability
- Minimum contrast: WCAG AA.
- Keyboard focus visible on all interactive controls.
- Touch target >= 36px.
- Avoid color-only status communication (add labels/icons).

## 9) Visual Polish
- Border radius: 8px (cards), 6px (inputs/buttons).
- Subtle shadows only on elevated elements.
- Use one icon style set consistently (stroke-based).
- Loading states: skeletons for tables/cards and spinner for short actions.

## 10) Suggested Delivery Phases
1. **Foundation:** tokens (colors, spacing, typography), button/input/table system.
2. **Navigation refresh:** sidebar + header consistency.
3. **Workflow pages:** Query, Merge, FTP/Drive page redesign patterns.
4. **Accessibility pass:** contrast, focus, keyboard checks.
5. **Polish pass:** micro-interactions, empty states, loading states.

---
Planning only. No implementation included.
