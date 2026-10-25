# Decision: evidence-driven adapter configuration

## Decision

Live portal paths and login field names are environment settings, not guessed constants.

## Why

The supplied brief contains no network capture. Guessing a route would create a polished but false integration. Configuration keeps the code honest and makes the eventual captured protocol easy to add.
