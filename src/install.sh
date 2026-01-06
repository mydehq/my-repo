#!/bin/bash

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color


# Logging functions (MyTM style)
log()         { echo -e "${BLUE}-${NC} $*" >&2; }
log.info()    { echo -e "${BLUE}i $* ${NC}" >&2;   }
log.success() { echo -e "${GREEN}+ $* ${NC}" >&2;  }
log.warn()    { echo -e "${YELLOW}! $* ${NC}" >&2; }
log.error()   { echo -e "${RED}x $* ${NC}" >&2;    }


has-cmd() {
  local cmd_str cmd_bin
  local exit_code=0

  [[ "$#" -eq 0 ]] && {
    log.error "No arguments provided."
    return 2
  }

  # Iterate over every argument passed to the function
  for cmd_str in "$@"; do
    cmd_bin="${cmd_str%% *}" # first token before any space


    if ! command -v "$cmd_bin" &>/dev/null; then
      exit_code=1
    fi
  done

  return "$exit_code"
}


# Check if running as root
if [ "$EUID" -ne 0 ]; then
    log.error "Please run as root (e.g. curl ... | sudo bash)"
    exit 1
fi

# Check if running on Arch Linux
if [[ ! -f /etc/arch-release ]]; then
    log.error "Why are you trying to install Arch repo in non-Arch Linux system?"
    exit 1
fi

# Check for required commands
if ! has-cmd "pacman curl grep sed"; then
    log.error "Missing required commands: pacman, curl, grep, sed"
    exit 1
fi

if grep -q "\[{{REPO_NAME}}\]" /etc/pacman.conf; then
    log.warn "Repository [{{REPO_NAME}}] already exists in /etc/pacman.conf"
else
    log.info "Adding [{{REPO_NAME}}] repository to /etc/pacman.conf..."
    cat <<EOF >> /etc/pacman.conf

[{{REPO_NAME}}]
SigLevel = Optional TrustAll
Server = {{REPO_URL}}/\$arch
EOF
    log.success "Repository added."
fi

log.info "Syncing database..."
pacman -Sy
