# QA regression assets

`tests/fixtures/parser_corpus.json` is the versioned offline contract for the five production HTML adapters and their checked-in HTML fixtures. `tests/test_parser_regression_corpus.py` executes every declared case without network access.

`tests/fixtures/data_quality_matrix.json` and `tests/test_data_quality_matrix.py` define deterministic expiry, conditions, geo and publication-readiness edge cases, including retry after `failed` and exclusion after `pending`/`published`.
