# 🔒 ADMIN DESIGN LOCK

Approved visual baseline: **2026-09-15**.

The current Crypto Exchange admin-panel design is the approved final design and must be treated as a protected visual baseline.

## Protected files
- `static/style.css`
- `templates/admin.html`
- `templates/admin_order.html`

## Rule
Do not redesign, replace, simplify, or overwrite these files during future functional changes.

Functional changes to the admin panel must preserve the existing:
- dark navy fintech background;
- blue / purple / teal gradients;
- sidebar and top navigation;
- statistics cards;
- exchange hero card;
- three-column order detail layout;
- status tracker and timeline;
- client/address cards;
- responsive mobile layout;
- typography, spacing, borders, shadows and buttons.

If a future feature requires changing the admin UI, modify only the minimum required area and preserve the established visual system.

## Baseline commits
- Admin dashboard CSS: `98285ac966d3e1be115798c4b9889d6e8f1fbb5e`
- Admin dashboard template: `97b0822f1fd6074b6c40b6988af30fe5d8e58cde`
- Admin order detail template: `5e968915c4d6cc10f564b08c7544738e702948bd`

**Important:** This file is a design contract for future work. New functionality must not cause the approved design to regress.