"""VELARA tracker analysis package.

Submodules:
    paths       - resolve bundled resources and pack files, independent of CWD
    loading     - read and lightly normalize the input pack
    countries   - derive the authoritative country list from the pack
    changes     - month-over-month diff detection (stub)
    rules       - rule checks that produce "findings" (stub registry)
    slippage    - per-country slippage/impact calculation (stub)
    ranking     - combine findings + slippage into the final risk_ranking
    validation  - structural checks against the output contract
"""
