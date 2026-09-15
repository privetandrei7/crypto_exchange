# 🔒 ADMIN DESIGN LOCK

Approved visual baseline: **2026-09-15**.

The Crypto Exchange admin panel now uses one unified dark neon fintech design across the **main dashboard and order-detail pages**.

## Protected files
- `static/style.css`
- `templates/admin.html`
- `templates/admin_order.html`

## Visual baseline
- dark navy fintech background;
- blue / purple / teal gradients;
- permanent left sidebar on desktop;
- unified top navigation;
- colorful KPI/stat cards;
- exchange hero card;
- clean cards for settings, rates, orders, users and system status;
- three-column order detail layout;
- status tracker and timeline;
- client/address cards;
- responsive mobile layout;
- established typography, spacing, borders, shadows and buttons.

## Rule
Do not redesign, replace, simplify, or overwrite the visual system during future functional changes.

If a future feature requires an admin UI change, modify only the minimum required area and preserve the existing visual language. New functionality must be integrated into the current design rather than creating a new visual style.

## Current approved commits
- Unified admin dashboard: `d4b6a15b07c20a174b7df2b85db558194edae99f`
- Admin/order styling baseline: `98285ac966d3e1be115798c4b9889d6e8f1fbb5e`
- Admin order detail template: `5e968915c4d6cc10f564b08c7544738e702948bd`

**Important:** This file is the design contract for future work. Do not regress or replace the approved admin design.