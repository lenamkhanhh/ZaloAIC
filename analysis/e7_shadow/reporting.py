"""CPU reporting only; never parse this into an executable call."""
import re


def pseudo_keyvalue(text):
    return bool(re.fullmatch(
        r'\s*sys\.ask_missing_info\s+tool_name=[a-z_][a-z0-9_]*\.[a-z_][a-z0-9_]*\s+params=\[[^\n]*\]\s*',
        text,
    ))
