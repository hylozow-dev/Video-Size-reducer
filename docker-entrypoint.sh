#!/bin/sh
# Runs as root at container start so it can fix ownership of mounted
# volumes (which may have been created previously with different
# permissions, e.g. before the image's user uid/gid was pinned to 101),
# then drops privileges to the unprivileged 'appuser' before running the
# actual application. This makes the container resilient to pre-existing
# volumes regardless of who created them.
set -e

if [ "$(id -u)" = "0" ]; then
    for dir in /app/storage; do
        if [ -d "$dir" ]; then
            chown -R appuser:appuser "$dir" 2>/dev/null || true
        fi
    done
    exec su appuser -s /bin/sh -c 'exec "$0" "$@"' -- "$@"
fi

exec "$@"
