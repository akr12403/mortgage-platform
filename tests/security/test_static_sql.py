"""M6 Task 6.3 (OWASP API8 / injection): static guard that every SQL statement is parameterised.

    python3 tests/security/test_static_sql.py      # stdlib only, no stack needed

Fails if application code builds SQL by string concatenation, f-strings, % or .format() — the only safe
pattern is placeholders (JPA/JPQL :name or ?, JdbcTemplate ?, SQLAlchemy text() with :name) plus bound values.
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
JAVA_SOURCES = sorted((ROOT / "services").glob("*/src/main/java/**/*.java"))
PY_SOURCES = sorted(p for p in (ROOT / "analytics").glob("*/src/**/*.py"))

SQL_WORD = r"(?:SELECT|INSERT|UPDATE|DELETE|MERGE|UPSERT|WHERE|FROM|VALUES|ORDER BY|GROUP BY)\b"

JAVA_RULES = [
    # "... WHERE x = '" + value   /   "SELECT ..." + var
    ("string concatenation into SQL", re.compile(r'"[^"\n]*' + SQL_WORD + r'[^"\n]*"\s*\+\s*[A-Za-z_(]', re.I)),
    # String.format("SELECT ... %s", ...)  /  "SELECT ... %s".formatted(...)
    ("String.format / formatted SQL", re.compile(r'(?:String\.format\(\s*"[^"\n]*' + SQL_WORD + r'|"[^"\n]*'
                                                  + SQL_WORD + r'[^"\n]*"\s*\.formatted\()', re.I)),
    # createNativeQuery / createQuery / jdbcTemplate.* called with a non-literal first argument built inline
    ("dynamic query argument", re.compile(r'(?:createNativeQuery|createQuery|\.query(?:ForObject|ForList)?|\.update|'
                                          r'\.execute)\(\s*[A-Za-z_][\w.]*\s*\+', re.I)),
]

PY_RULES = [
    ("f-string SQL", re.compile(r'\b[fF][rR]?(?:"""|\'\'\'|"|\')[^"\']*' + SQL_WORD, re.I)),
    ("%-formatted SQL", re.compile(r'(?:"""|"|\')[^"\']*' + SQL_WORD + r'[^"\']*%s[^"\']*(?:"""|"|\')\s*%', re.I)),
    (".format() SQL", re.compile(r'(?:"""|"|\')[^"\']*' + SQL_WORD + r'[^"\']*(?:"""|"|\')\s*\.format\(', re.I | re.S)),
    ("execute() with concatenation", re.compile(r'\.execute\(\s*(?:text\()?\s*(?:"[^"]*"|\'[^\']*\')\s*\+')),
]


def _violations(paths, rules):
    found = []
    for path in paths:
        source = path.read_text(encoding="utf-8")
        for label, pattern in rules:
            for match in pattern.finditer(source):
                snippet = match.group(0)
                # Log lines and exception messages are not SQL
                line = source[source.rfind("\n", 0, match.start()) + 1: source.find("\n", match.end())]
                if re.search(r"\b(log(?:ger)?\.\w+|raise|throw|message|detail|description)\b", line, re.I):
                    continue
                lineno = source.count("\n", 0, match.start()) + 1
                found.append(f"{path.relative_to(ROOT)}:{lineno}: {label}: {snippet.strip()[:100]}")
    return found


class StaticSqlTest(unittest.TestCase):

    def test_sources_were_found(self):
        self.assertTrue(JAVA_SOURCES, "no Java sources found")
        self.assertTrue(PY_SOURCES, "no analytics sources found")

    def test_java_sql_is_parameterised(self):
        self.assertEqual(_violations(JAVA_SOURCES, JAVA_RULES), [])

    def test_python_sql_is_parameterised(self):
        self.assertEqual(_violations(PY_SOURCES, PY_RULES), [])

    def test_the_guard_actually_catches_injection(self):
        # Self-test so a broken regex cannot make the guard pass silently.
        bad_java = 'jdbcTemplate.query("SELECT * FROM mortgage WHERE id = \'" + id + "\'", mapper);'
        bad_py = 'db.execute(text(f"SELECT id FROM mortgage WHERE mortgage_external_id = \'{ext}\'"))'
        self.assertTrue(any(p.search(bad_java) for _, p in JAVA_RULES))
        self.assertTrue(any(p.search(bad_py) for _, p in PY_RULES))
        good_py = 'db.execute(text("SELECT id FROM mortgage WHERE mortgage_external_id = :ext_id"), {"ext_id": ext})'
        self.assertFalse(any(p.search(good_py) for _, p in PY_RULES))


if __name__ == "__main__":
    unittest.main(verbosity=2)
