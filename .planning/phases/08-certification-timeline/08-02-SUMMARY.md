---
phase: "08"
plan: "02"
subsystem: mobile
tags: [journey-timeline, certificate, view-shot, sharing, caching]
dependency-graph:
  requires: [08-01]
  provides: [journey-timeline-screen, certificate-screen, certificate-sharing]
  affects: [festival-wrapup]
tech-stack:
  added: [expo-media-library, react-native-view-shot]
  patterns: [forwardRef-capture, async-storage-cache, linear-gradient-template]
key-files:
  created:
    - festapp-mobile/features/points/hooks/useJourneyTimeline.ts
    - festapp-mobile/features/points/hooks/useCertificateData.ts
    - festapp-mobile/features/points/hooks/useCertificateCache.ts
    - festapp-mobile/features/points/components/JourneyTimeline.tsx
    - festapp-mobile/features/points/components/CertificateView.tsx
    - festapp-mobile/app/certificate.tsx
  modified:
    - festapp-mobile/api/schemas.ts
    - festapp-mobile/api/features/rewards.ts
    - festapp-mobile/features/points/hooks/index.ts
    - festapp-mobile/app/festival-wrapup.tsx
    - festapp-mobile/package.json
decisions:
  - Used `as never` cast for router.push("/certificate") to match existing codebase pattern for typed routes
  - CertificateView rendered off-screen at left:-9999 with pointerEvents="none" for capture
  - Used collapsable={false} on CertificateView outer View for Android compatibility
metrics:
  duration: "6 minutes"
  completed: "2026-03-16"
---

# Phase 8 Plan 02: Mobile Journey Timeline and Certificate Screens Summary

Journey timeline component, certificate generation with view-shot capture, sharing via expo-sharing, and photo save via expo-media-library with AsyncStorage-based template version caching.

## What Was Built

### Task 1: Dependencies, API Types, Functions, and Hooks

- **Installed** `expo-media-library` and `react-native-view-shot` dependencies
- **Added 7 TypeScript types** to `api/schemas.ts`: TimelineEventOut, TimelineDayOut, JourneyTimelineOut, MilestoneRankOut, CertificateTemplateConfig, CertificateDataOut
- **Added 2 API functions** to `api/features/rewards.ts`: getJourneyTimeline, getCertificateData
- **Created 3 hooks**: useJourneyTimeline (React Query), useCertificateData (React Query), useCertificateCache (AsyncStorage with template version invalidation)
- **Updated hooks index** with new exports

### Task 2: Components, Screens, and Wrapup Integration

- **JourneyTimeline component**: Day-grouped activity feed with color-coded event types (session=blue, group=green, scan=amber, message=purple, meeting=red, poll=cyan), vertical timeline line, empty state, total activities count
- **CertificateView component**: 375x530 fixed-size forwardRef View for PNG capture, LinearGradient background from template config, decorative border, festival name/tagline, user name, top 3 milestone badges with rank labels, footer
- **Certificate screen** (`app/certificate.tsx`): Full certificate generation flow with captureRef, cached image check on mount, generate/regenerate/share/save-to-photos actions, loading/error states, dark theme
- **Updated festival-wrapup.tsx**: Added journey timeline section before Key Milestones, updated certificate CTA to navigate to `/certificate` screen, added timeline refetch to pull-to-refresh

## Verification

TypeScript check passed for all new and modified files. Pre-existing errors in unrelated files (schedule, networking) remain unchanged.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Fixed typed route error for /certificate**
- **Found during:** Task 2
- **Issue:** Expo Router typed routes didn't recognize `/certificate` as a valid route parameter
- **Fix:** Used `as never` cast matching existing codebase pattern (same issue exists for other routes)
- **Files modified:** `app/festival-wrapup.tsx`

## Commits

| Task | Commit | Description |
|------|--------|-------------|
| 1 | 7ca71f2 | Types, API functions, hooks, dependencies |
| 2 | b9eb067 | Components, certificate screen, wrapup integration |

## Self-Check: PASSED

All 10 files verified as existing. Both commits verified in git log.
