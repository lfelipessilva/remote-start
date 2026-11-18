# Shutdown Modal Feedback Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Keep the shutdown configuration modal open during the SSH configuration process to display live loading, detailed error messages with retry, copy fallback command, and success feedback directly inside the modal.

**Architecture:** Move SSH shutdown configuration logic and status presentation into `ShutdownSetupDialog` in `src/ShutdownSetupModal.tsx`. `SettingsView.tsx` will pass an `onConfigured` callback that receives the configured username when the process succeeds.

**Tech Stack:** React, TypeScript, Rollup, `@decky/ui`, `@decky/api`.

## Global Constraints
- Do not close the modal on submit.
- Maintain seamless gamepad/keyboard navigation with `@decky/ui` components (`ConfirmModal`, `TextField`, `ButtonItem`).
- Maintain zero passwords persisted in state or files.

## Review Focus
1. Loading state disables inputs and buttons to prevent double-submission.
2. Error state allows fixing credentials and retrying without closing the modal.
3. Fallback command is copyable if provided in the error response.
4. Success state clearly presents confirmation and changes the action to a "Done" button.
5. Builds cleanly with `pnpm run build` and tests pass.

---

### Task 1: Update `src/ShutdownSetupModal.tsx` to handle async execution, loading, error, and success states

**Files:**
- Modify: `src/ShutdownSetupModal.tsx`

**Steps:**
- [ ] Add imports for `configureShutdown` from `./api` and `ButtonItem` from `@decky/ui`.
- [ ] Update `ShutdownSetupDialog` to manage `busy`, `error`, `command`, `success`, and `copied` state.
- [ ] Implement `handleSubmit` to call `configureShutdown(user.trim(), password)` without closing the modal.
- [ ] In loading state (`busy`), disable fields, disable OK button with "Connecting…", and show status description.
- [ ] In error state, display error message in red, set button text to "Try again", and display copyable fallback command button if returned.
- [ ] In success state, show success message in green, call `onConfigured`, and set button to "Done" (`bAlertDialog: true`).

### Task 2: Update `src/SettingsView.tsx` to use the updated `openShutdownSetup` signature

**Files:**
- Modify: `src/SettingsView.tsx`

**Steps:**
- [ ] Update `setupShutdown` in `src/SettingsView.tsx` to pass `(user) => { setForm(f => ({ ...f, ssh_user: user })); setShutdownMsg("Shutdown configured. The password was not saved."); }`.
- [ ] Ensure `form.ssh_user` and settings view status reflect the result when the modal is closed.

### Task 3: Build and Verify

**Files:**
- Build outputs: `dist/index.js`

**Steps:**
- [ ] Run `pnpm run build` and verify bundle builds with zero errors.
- [ ] Run `pytest` and verify backend tests pass.
- [ ] Verify TypeScript types compile cleanly.
