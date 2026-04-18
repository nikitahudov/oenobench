"""Team agents for the OenoBench audit.

Each module exposes one or more `run_*(run_id, questions) -> list[finding_dict]`
functions. Findings are plain dicts ready for `_findings.write_finding`.
"""
