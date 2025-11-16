## Assistant Guidelines

- Always execute project tooling through `python dev.py <command>`.
- Default to English for comments, docstrings, and translations.
- Keep comments minimal and only when they clarify non-obvious logic.
- Avoid reiterating what the code already states clearly.
- Add comments only when they resolve likely ambiguity or uncertainty.
- Do not introduce any dependency on Django (imports, settings, or implicit coupling).
- Each provider must implement every service family implied by `supported_types`, covering the full trio of `send_*`, `cancel_*`, and `check_*_delivery_status` helpers plus matching `get_*_service_info`, `calculate_*_delivery_risk`, and `handle_*_webhook` / `validate_*_webhook_signature` methods.
- When adding helper-style utilities or tests, review `python_missive/helpers.py` for existing shortcuts before introducing new loader logic.
- **Provider Testing**: For testing generic provider methods (send, cancel, check, risk, info), use the generic test system in `tests/test_providers.py` via `dev.py test_providers <provider> <service> <method>` instead of creating separate test files. Example: `python dev.py test_providers smspartner sms info` to test `get_sms_service_info`. Only create separate test files for provider-specific logic that cannot be tested generically.
- Providers list and loading: Never hardcode the list of providers anywhere. Always resolve providers via configuration or `python_missive/helpers.py` (dynamic loading/registry). Any new logic must respect this indirection.

- Geographic scope rules:
  - Use `data/countries.csv` as the single source of truth for regions/subregions/country codes.
  - The token `*` means “no geographic limitation”.
  - Each provider MUST declare a geographic scope per service family via config keys:
    `postal_geo`, `email_geo`, `sms_geo`, `push_geo`, `voice_geo`, `branded_geo`, `notification_geo`, `lre_geo`, `rcs_geo`.
  - Values can be `*`, a comma-separated string, or a list of tokens mixing:
    ISO codes (CCA2/CCA3), country common names (case-insensitive), regions or subregions from the dataset.
  - Never hardcode country lists in code; rely on configuration and the dataset for validation.

