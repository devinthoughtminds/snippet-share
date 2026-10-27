import pytest

from scanner import redact, scan

# Built from parts so this file doesn't itself look like it leaks secrets.
AWS = "AKIA" + "IOSFODNN7EXAMPLE"
GITHUB = "ghp_" + "a" * 36
GOOGLE = "AIza" + "B" * 35
SLACK = "xoxb-" + "1234567890-abcdef"
SK = "sk-" + "proj-" + "c" * 30
JWT = "eyJ" + "hbGciOiJIUzI1NiJ9" + ".eyJ" + "zdWIiOiIxMjM0In0" + "." + "d" * 20
KEY = "-----BEGIN RSA PRIVATE KEY-----\nMIIEow\nabc\n-----END RSA PRIVATE KEY-----"


@pytest.mark.parametrize(
    "text, kind",
    [
        (f"key = '{AWS}'", "aws_access_key"),
        (f"token: {GITHUB}", "github_token"),
        (f"maps({GOOGLE})", "google_api_key"),
        (f"SLACK={SLACK}", "slack_token"),
        (f"client = OpenAI(api_key='{SK}')", "api_key"),
        (f"Authorization: Bearer {JWT}", "jwt"),
        (KEY, "private_key"),
        ("postgresql://snippet:hunter2pass@db:5432/x", "url_password"),
        ('password = "Sup3rS3cret!"', "password_assignment"),
        ("DB_PASSWORD=Sup3rS3cret", "env_secret"),
    ],
)
def test_finds_each_kind(text, kind):
    findings = scan(text)
    assert [f["type"] for f in findings] == [kind]


def test_reports_line_and_never_returns_the_secret():
    text = f"import os\n\nAWS_KEY = '{AWS}'\n"
    [finding] = scan(text)
    assert finding["line"] == 3
    assert AWS not in str(finding)
    assert finding["preview"].startswith("AKIA")


def test_password_preview_shows_nothing_of_the_value():
    [finding] = scan('password = "Sup3rS3cret!"')
    assert "Sup3" not in finding["preview"]


@pytest.mark.parametrize(
    "text",
    [
        "def add(a, b):\n    return a + b\n",
        'password = os.environ["DB_PASSWORD"]',
        "password = get_password()",
        "MCP_PASSWORD=change-me",
        "API_KEY=${API_KEY}",
        'token = "<your-token-here>"',
        "postgresql://user@localhost/db",
    ],
)
def test_ignores_normal_code_and_placeholders(text):
    assert scan(text) == []


def test_one_secret_is_reported_once():
    # The JWT also sits in a `token = "..."` assignment; it must not count twice.
    assert len(scan(f'token = "{JWT}"')) == 1


def test_redact_replaces_only_the_secrets():
    text = f"url = 'postgresql://u:hunter2pass@db/x'\n\tkey = {AWS}  # keep me\n"
    assert redact(text) == "url = 'postgresql://u:[REDACTED:url_password]@db/x'\n\tkey = [REDACTED:aws_access_key]  # keep me\n"


def test_redact_leaves_clean_text_untouched():
    text = "a\r\n  b\t😀\n"
    assert redact(text) == text


@pytest.mark.parametrize("text", ['db_password = "Tr0ub4dor&3x"', "smtp-api-key: 'k8Jq2LmZ9xP4'", 'GH_TOKEN: "a8f5f167f44f4964"'])
def test_finds_assignment_with_prefixed_name(text):
    assert [f["type"] for f in scan(text)] == ["password_assignment"]


@pytest.mark.parametrize("text", ['password_hint = "remember the dog"', 'aws_secret_region = "eu-west-1x"'])
def test_prefixed_rule_still_needs_whole_keyword(text):
    assert scan(text) == []
