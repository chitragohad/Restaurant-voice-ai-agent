---
name: Heritage Tech
colors:
  surface: '#0f1419'
  surface-dim: '#0f1419'
  surface-bright: '#353a3f'
  surface-container-lowest: '#0a0f14'
  surface-container-low: '#171c21'
  surface-container: '#1b2025'
  surface-container-high: '#252a30'
  surface-container-highest: '#30353b'
  on-surface: '#dee3ea'
  on-surface-variant: '#d5c4af'
  inverse-surface: '#dee3ea'
  inverse-on-surface: '#2c3136'
  outline: '#9d8e7c'
  outline-variant: '#504535'
  surface-tint: '#fdba49'
  primary: '#ffc66b'
  on-primary: '#432c00'
  primary-container: '#e8a838'
  on-primary-container: '#5f3f00'
  inverse-primary: '#805600'
  secondary: '#ffb5a0'
  on-secondary: '#601500'
  secondary-container: '#802a10'
  on-secondary-container: '#ff9b7f'
  tertiary: '#58ea8a'
  on-tertiary: '#003919'
  tertiary-container: '#34cd71'
  on-tertiary-container: '#005126'
  error: '#ffb4ab'
  on-error: '#690005'
  error-container: '#93000a'
  on-error-container: '#ffdad6'
  primary-fixed: '#ffddaf'
  primary-fixed-dim: '#fdba49'
  on-primary-fixed: '#281800'
  on-primary-fixed-variant: '#614000'
  secondary-fixed: '#ffdbd1'
  secondary-fixed-dim: '#ffb5a0'
  on-secondary-fixed: '#3b0900'
  on-secondary-fixed-variant: '#802a10'
  tertiary-fixed: '#6dfe9c'
  tertiary-fixed-dim: '#4de082'
  on-tertiary-fixed: '#00210c'
  on-tertiary-fixed-variant: '#005227'
  background: '#0f1419'
  on-background: '#dee3ea'
  surface-variant: '#30353b'
typography:
  display-logo:
    fontFamily: Libre Caslon Text
    fontSize: 32px
    fontWeight: '600'
    lineHeight: 40px
    letterSpacing: 0.02em
  headline-lg:
    fontFamily: Plus Jakarta Sans
    fontSize: 32px
    fontWeight: '600'
    lineHeight: 40px
  headline-sm:
    fontFamily: Plus Jakarta Sans
    fontSize: 20px
    fontWeight: '600'
    lineHeight: 28px
  body-md:
    fontFamily: DM Sans
    fontSize: 16px
    fontWeight: '400'
    lineHeight: 24px
  body-sm:
    fontFamily: DM Sans
    fontSize: 14px
    fontWeight: '400'
    lineHeight: 20px
  label-caps:
    fontFamily: DM Sans
    fontSize: 12px
    fontWeight: '500'
    lineHeight: 16px
    letterSpacing: 0.05em
  code-res:
    fontFamily: JetBrains Mono
    fontSize: 16px
    fontWeight: '500'
    lineHeight: 24px
rounded:
  sm: 0.25rem
  DEFAULT: 0.5rem
  md: 0.75rem
  lg: 1rem
  xl: 1.5rem
  full: 9999px
spacing:
  base: 8px
  xs: 4px
  sm: 12px
  md: 24px
  lg: 40px
  max_width: 520px
  gutter: 16px
---

## Brand & Style

The design system embodies "Warm North Indian hospitality meets modern, frictionless technology." The aesthetic is **Modern Minimalist with Tactile Accents**, focusing on a high-end, dark-mode experience that feels premium and serene. 

The UI should evoke a sense of calm efficiency, utilizing heavy whitespace (or "dark space") to let the golden accents signify value and focus. We balance the heritage of the brand with the precision of a voice-first interface by pairing elegant serif flourishes with high-performance geometric sans-serifs. The goal is to move the user from a state of hunger/stress to a state of being "hosted" through a reliable, sophisticated digital concierge.

## Colors

This design system utilizes a deep, nocturnal palette to establish a premium atmosphere. The **Saffron Gold** (Primary) is the focal point, used for calls-to-action and critical status indicators. 

- **Primary & Secondary:** Saffron Gold is used for brand presence and primary actions. Terracotta is reserved for celebratory highlights or specific badges, ensuring it doesn't compete with the gold.
- **Backgrounds:** A three-tier dark system is used: Deep Midnight for the canvas, Slate Navy for interactive cards, and a subtle Grey-Blue for hover states.
- **Functional Colors:** Soft Emerald signals an active, listening state for the voice interface, while Muted Coral Red handles errors and session termination.
- **Accents:** Use gold dividers at 20% opacity to maintain a sense of luxury without creating visual clutter.

## Typography

The typography system is designed for high legibility in low-light environments. 

- **Brand Expression:** While the logo uses a classic serif (modeled by Libre Caslon Text), the UI relies on **Plus Jakarta Sans** for structure and **DM Sans** for utility.
- **Hierarchy:** Use the Display role for the restaurant name and welcome messages. Headline-LG is for primary intent (e.g., "Confirming your table"). 
- **Utility:** Use **JetBrains Mono** exclusively for reservation codes and technical identifiers to prevent character confusion (e.g., distinguishing '0' from 'O').
- **Accessibility:** Minimum body size is 14px. Ensure a 4.5:1 contrast ratio between text and background at all times.

## Layout & Spacing

The layout is **Mobile-First and Centered**. To mimic the intimacy of a personal conversation, the content is constrained to a 520px maximum width, ensuring that even on desktop, the interface feels like a focused, handheld tool.

- **The Grid:** A single-column fluid layout with 16px side gutters.
- **Rhythm:** Spacing follows an 8px base unit. Use `lg` (40px) spacing to separate major sections (e.g., Header from the Mic UI), and `md` (24px) for spacing inside cards.
- **Tap Targets:** All interactive elements must maintain a minimum height/width of 48px to ensure accessibility for all users.

## Elevation & Depth

Depth is conveyed through **Tonal Layering** and **Luminous Accents** rather than traditional heavy shadows.

- **Surface Levels:** 
  1. Base: Deep Midnight (#0F1419) - The ground.
  2. Elevated: Slate Navy (#1A2332) - Interactive cards and containers.
  3. Overlay: Subtle Grey-Blue (#232D3F) - Context menus or hover states.
- **Shadows:** Avoid shadows on secondary elements. Apply a vibrant **Saffron Glow** (`0 8px 32px rgba(232,168,56,0.25)`) only to the Primary Mic Button or active CTAs to make them appear as if they are emitting light.
- **Dividers:** Use 1px borders with 6% white or 20% gold opacity to create delicate structure without breaking the visual flow.

## Shapes

The shape language combines geometric precision with soft, organic curves.

- **Cards:** Use a 16px (`rounded-lg`) radius to create a friendly, approachable container.
- **Pills:** Use 999px for status badges and secondary buttons to differentiate them from the primary structure.
- **Circular:** The Voice/Mic button and specific icons are 50% circular to emphasize their tactile, "push-to-talk" nature.
- **Visual Motif:** Incorporate a faint mandala or paisley watermark at 3% opacity inside card backgrounds to ground the modern UI in traditional Indian artistry.

## Components

### Buttons
- **Primary (Mic):** A 72px or 96px circle with the Saffron gradient. On "Listening," it should have a subtle pulse animation.
- **Secondary:** Outlined with #E8A838 (20% opacity), text in primary gold.
- **Tertiary:** Text-only with a gold focus ring for accessibility.

### Cards
- Background: #1A2332.
- Border: 1px rgba(255,255,255,0.06).
- Pattern: Faint paisley watermark positioned in the bottom-right corner.

### Status Badges
- **Idle:** Grey-Blue background with muted text.
- **Listening:** Soft Emerald background with dark text; includes a small waveform icon.
- **Error:** Muted Coral Red with a white/ivory icon.

### Inputs & Selection
- **Reservation Code:** Displayed in a card with #232D3F background, using JetBrains Mono for the text. Provide a "Copy" icon button as a 48px tap target.
- **Voice Feedback:** A real-time visualizer (simple 3-line waveform) in Saffron Gold that reacts to user voice input.

### Icons
- Use 24px thin-line art. Specifically, use a stylized Lotus for "Home/Success" and a Diya for "Special Requests" or "Settings."