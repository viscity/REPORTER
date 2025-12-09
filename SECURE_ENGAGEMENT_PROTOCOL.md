# Secure Engagement Protocol (SEP)

This master document defines the required environment configuration and UI/UX behaviors that enforce strict limits on user reactions and concurrent logins.

## Part 1: System Configuration (Backend Logic)

The following parameters are immutable, environment-level variables that govern core application behavior. They must be set in configuration files (for example, `.env`, `config.yaml`) and cannot be changed by any users or administrators.

| Parameter Key | Value | Description | Immutability Status |
| --- | --- | --- | --- |
| `SEP_MAX_REACTIONS_PER_RESOURCE` | `5` | Maximum number of times a single user can apply any reaction (like, emoji, etc.) to a specific content item (post, photo, comment). | **HARD LIMIT (Config-Locked)** |
| `SEP_MAX_CONCURRENT_SESSIONS` | `1` | Maximum number of simultaneous, active login sessions a single user account can maintain across all devices. | **HARD LIMIT (Config-Locked)** |
| `SEP_MASS_REACTION_PREVENTION` | `TRUE` | Global flag confirming the activation of low, hardcoded reaction limits to prevent abuse. | **SYSTEM DEFAULT** |

### Deployment Compatibility Note

These environment variables (`KEY=VALUE`) are compatible with:

- **Linux VPS / Bare Metal**: Loaded via environment profiles (`.bashrc`), service files (`systemd`), or process managers (`PM2`).
- **Heroku**: Set directly as Config Vars in the dashboard/CLI.
- **Termux (Testing/Dev)**: Set via the `export` command in the shell environment.

## Part 2: User Interface & Experience (User View)

### Reaction Limit Enforcement UI

| Component | UI Specification | User-Facing Text (Copy) | UX Flow |
| --- | --- | --- | --- |
| Notification Type | Toast/Snack Bar (2.5s duration, high visibility) | **Max Reaction Limit Reached** | User attempts the 6th reaction. |
| Icon/Style | 🚫 (Red/Warning color); subtle shake on the Reaction button. | You have reached the maximum limit of 5 reactions for this content. | Reaction button (icon) count remains at its maximum value (5). |
| Action | None (Auto-dismiss) |  | Request is blocked server-side (403 Forbidden). |

### Concurrent Session Control UI

| Component | UI Specification | User-Facing Text (Copy) | UX Flow |
| --- | --- | --- | --- |
| New Login Device (Device B) | Successful login with a brief success toast. | **Welcome back!** | New session is created. |
| Previous Device (Device A) | Mandatory Modal Alert (Center Screen, requires interaction) | **Session Terminated** | Old session (Device A) is invalidated. |
| Body Text | Clear explanation for session closure. | You have logged in on another device. Your session on this device has been automatically closed to enforce the maximum concurrent session limit. |  |
| Action Button | Primary Action Button (Solid Color) | **Re-Login / Got It** | Closes the modal and takes the user back to the Login screen. |

## Part 3: Text Summary for Direct Integration

Use the following strings verbatim in the UI:

| Context | Text String |
| --- | --- |
| Reaction Limit Title | Max Reaction Limit Reached |
| Reaction Limit Body | You have reached the maximum limit of 5 reactions for this content. |
| Session Alert Title | Session Terminated |
| Session Alert Body | You have logged in on another device. Your session on this device has been automatically closed to enforce the maximum concurrent session limit. |
| Session Alert Button | Got It |

This document serves as the single source of truth for both engineering (configuration) and design (UI/UX) teams.
