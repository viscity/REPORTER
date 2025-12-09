#!/usr/bin/env python3
"""Simple integrity-check example for educational purposes.

The script stores a hashed author ID and verifies at runtime that the
provided author name hashes to the same value. If the stored hash is
altered or the author name differs, the integrity check fails.
"""

import hashlib
import sys
from typing import Tuple

# Store only the hashed author ID in the code. This makes it harder to
# tamper with the expected author name, because you are comparing against
# a stable digest instead of a raw string.
STORED_AUTHOR_HASH = "c5c8cd48384b065a0e46d27016b4e3ea5c9a52bd12d87cd681bd426c480cce3a"


def hash_author(name: str) -> str:
    """Return the SHA-256 hex digest for the provided author name."""

    return hashlib.sha256(name.encode("utf-8")).hexdigest()


def verify_author(name: str) -> Tuple[bool, str]:
    """Check whether the provided name matches the stored author hash.

    Returns a tuple of (is_valid, computed_hash). The calling code can
    print helpful information about what was checked.
    """

    computed_hash = hash_author(name)
    is_valid = computed_hash == STORED_AUTHOR_HASH
    return is_valid, computed_hash


def main() -> None:
    # Use a command-line argument when provided, otherwise fall back to
    # the expected author ID. This keeps the example simple while still
    # letting you experiment with different inputs.
    author_name = sys.argv[1] if len(sys.argv) > 1 else "oxeign"

    # Recompute the hash at runtime to confirm the constant was not
    # modified and that the supplied author name matches the original
    # value used to build the stored hash.
    is_valid, computed_hash = verify_author(author_name)

    print(f"Stored author hash: {STORED_AUTHOR_HASH}")
    print(f"Computed hash for '{author_name}': {computed_hash}")

    if not is_valid:
        print("Integrity check failed: unauthorized modification.")
        return

    print("Integrity check passed: author ID verified.")


if __name__ == "__main__":
    main()
