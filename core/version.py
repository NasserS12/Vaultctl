"""Single source of truth for the displayed version tag.

Bump this manually on release — kept independent of `git describe` so
the tool still shows a sane version when run from a zip/tarball
checkout with no .git directory.
"""

VERSION = "1.1.1"
