"""bundle.sh signs with a stable local identity when one exists (2026-09-30).

An ad-hoc signature's designated requirement is the build's cdhash, so macOS
asked for microphone and location again after every deploy. These checks keep
bundle.sh from sliding back to ad-hoc-only signing."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BUNDLE = ROOT / "macos" / "MortimerHost" / "scripts" / "bundle.sh"
SETUP = ROOT / "scripts" / "setup_signing_identity.sh"


def test_bundle_signs_with_the_local_identity_when_present():
    text = BUNDLE.read_text(encoding="utf-8")
    assert 'MORTIMER_SIGN_IDENTITY:-Mortimer Local Code Signing' in text
    assert "security find-identity -p codesigning" in text
    assert 'codesign --force --sign "$SIGN" "$APP"' in text
    signing_lines = [l.strip() for l in text.splitlines() if l.strip().startswith("codesign --force")]
    assert signing_lines and all('"$SIGN"' in l for l in signing_lines), signing_lines


def test_setup_script_creates_a_code_signing_identity_with_the_same_name():
    text = SETUP.read_text(encoding="utf-8")
    assert 'MORTIMER_SIGN_IDENTITY:-Mortimer Local Code Signing' in text
    assert "extendedKeyUsage = critical,codeSigning" in text
    assert "add-trusted-cert -r trustRoot -p codeSign" in text
