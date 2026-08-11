# v1.0.0
- Modern and easy-to-use GUI
- Updated GSE
- Automated achievement generation
- Updated build script
- Improved startup time

# v1.0.1
- Fixed issues with achievement fetching
- Resolved hidden descriptions for achievements

# v1.0.2
- Updated GBE fork

# v1.0.3
- Disabled maximize button to prevent layout issues
- Added placeholders to textboxes
- Refactored closing function
- Enabled automatic download of 7z.dll via the workflow
- Added Quick Guide in GUI

# v1.0.4
- Refactored session creation logic
- Added support for external header files for better maintainability

# v1.0.5
- Removed `headers.dat` functionality
- Included functionality for reliable achievement fetching 
- Improved image downloading logic
- Added thread safety with mutex protection

# v1.0.6
- Fixed executable window title
- Refactored error messages
- Added fallback mechanism for APP_ID resolution
- Improved browser detection for broader compatibility

# v1.0.7
- Introduced a Browse button for easy game lookup and selection
- Completely overhauled `cf_bypass.py` with a more robust stealth mechanism
- Introduced `StealthShield` to intercept and hide browser windows more effectively
- Improved `CloudflareBypasser` with refined Turnstile detection and interaction
- Modularized GUI layer by extracting components into a dedicated `widgets` package
- Centralized core logic and improved separation of concerns
- Introduced `network.py` to unify session management and file downloads
- Implemented `logger.py` to improve debugging and error tracking across modules
- Reduced code duplication across all core modules

# v1.0.8
- Replaced browser-based Cloudflare bypass with native `cf_bypass.dll`
- Removed DrissionPage dependency
- Overhauled SteamDB extraction with robust selectors
- Improved hidden-achievement and icon detection

# v1.0.9
- Replaced standard python threading with PySide6 synchronization primitives
- Fixed a critical deadlock bug in `cf_bypass.py` by switching to recursive locking
- Added robust challenge-page detection in Python to automatically retry failed Cloudflare solver attempts
- Optimized startup warmup speed by fetching only clearance cookies and skipping page body parsing
