#!/usr/bin/env bash
# Chat-managed machines never create a fresh public session on an ordinary reboot.
set -euo pipefail
printf '%s\n' 'Black Cat cloud workspace ready. Use the Chat Control workflow to start DNS.'
printf '%s\n' 'No public DNS service was started by this boot hook.'
