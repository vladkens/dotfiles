#!/bin/sh
# Replacing this repository can leave shell configs missing or their links broken,
# so PATH may no longer include Homebrew. Bootstrap deploy without those configs:
# preserve existing PATH entries, append missing tool directories, and export the
# result so Dotter and its hooks can find their tools. Run via /bin/sh even if PATH
# is empty; locate the repository from this script rather than the caller's cwd.
set -eu

append_path() {
    case ":${PATH-}:" in
        *":$1:"*) ;;
        *) PATH="${PATH:+$PATH:}$1" ;;
    esac
}

for directory in /usr/bin /bin /usr/sbin /sbin; do
    append_path "$directory"
done

export PATH

if ! command -v brew >/dev/null 2>&1; then
    for prefix in /opt/homebrew /usr/local; do
        if [ -x "$prefix/bin/brew" ]; then
            append_path "$prefix/bin"
            break
        fi
    done
fi

if ! command -v brew >/dev/null 2>&1; then
    echo "Homebrew not found. Install Homebrew before deploying." >&2
    exit 1
fi

brew_prefix=$(brew --prefix)
append_path "$brew_prefix/bin"
append_path "$brew_prefix/sbin"

if ! command -v dotter >/dev/null 2>&1; then
    echo "Dotter not found. Install it with: $brew_prefix/bin/brew install dotter" >&2
    exit 1
fi

cd "$(dirname "$0")/.."
exec dotter --pre-deploy .dotter/pre-deploy.sh --post-deploy .dotter/post-deploy.sh deploy --force --noconfirm --verbose
