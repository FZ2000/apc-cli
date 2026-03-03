#!/usr/bin/env bash
set -euo pipefail

REPO="https://github.com/FZ2000/apc-cli.git"
INSTALL_DIR="${APC_INSTALL_DIR:-$HOME/.apc-cli}"
BIN_DIR="${APC_BIN_DIR:-$HOME/.local/bin}"

info()  { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
error() { printf '\033[1;31merror:\033[0m %s\n' "$*" >&2; exit 1; }

# Check Python >= 3.12
check_python() {
    for cmd in python3 python; do
        if command -v "$cmd" &>/dev/null; then
            version=$("$cmd" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
            major=$("$cmd" -c "import sys; print(sys.version_info.major)")
            minor=$("$cmd" -c "import sys; print(sys.version_info.minor)")
            if [ "$major" -ge 3 ] && [ "$minor" -ge 12 ]; then
                PYTHON="$cmd"
                return
            fi
        fi
    done
    error "Python 3.12+ is required. Found: ${version:-none}"
}

check_python
info "Using $PYTHON ($($PYTHON --version))"

# Clone or update
if [ -d "$INSTALL_DIR" ]; then
    info "Updating existing installation..."
    git -C "$INSTALL_DIR" pull --ff-only
else
    info "Cloning apc-cli..."
    git clone "$REPO" "$INSTALL_DIR"
fi

# Create venv and install
info "Setting up virtual environment..."
"$PYTHON" -m venv "$INSTALL_DIR/.venv"
"$INSTALL_DIR/.venv/bin/pip" install --quiet --upgrade pip
"$INSTALL_DIR/.venv/bin/pip" install --quiet "$INSTALL_DIR"

# Create bin directory and symlink
mkdir -p "$BIN_DIR"
ln -sf "$INSTALL_DIR/.venv/bin/apc" "$BIN_DIR/apc"

# Check if BIN_DIR is in PATH
if ! echo "$PATH" | tr ':' '\n' | grep -qx "$BIN_DIR"; then
    info "Add this to your shell profile:"
    echo ""
    echo "  export PATH=\"$BIN_DIR:\$PATH\""
    echo ""
fi

info "Installed apc $("$INSTALL_DIR/.venv/bin/apc" --version 2>&1 | awk '{print $NF}')"
info "Run 'apc --help' to get started"
