from lc_demo.config import redact


def test_redact_hides_password():
    url = "postgresql://neondb_owner:npg_s3cret@ep-cool-name-123.us-east-2.aws.neon.tech/neondb?sslmode=require"
    assert redact(url) == "postgresql://neondb_owner:***@ep-cool-name-123.us-east-2.aws.neon.tech/neondb?sslmode=require"


def test_redact_leaves_passwordless_urls_alone():
    assert redact("postgresql://localhost:5433/lc_demo") == "postgresql://localhost:5433/lc_demo"
