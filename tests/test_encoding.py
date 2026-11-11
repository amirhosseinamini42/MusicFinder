import importlib.util
import pathlib
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent


class EncodingTests(unittest.TestCase):
    def test_python_accepts_utf8_bom_sources(self):
        """A UTF-8 BOM does not break imports (CPython strips it), so BOM is hygiene, not a startup blocker."""
        with tempfile.TemporaryDirectory() as d:
            p = pathlib.Path(d) / "bom_mod.py"
            p.write_bytes(b"\xef\xbb\xbf" + b'"""doc"""\nVALUE = 7\n')
            spec = importlib.util.spec_from_file_location("bom_mod", p)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            self.assertEqual(mod.VALUE, 7)

    def test_agent_sources_have_no_bom(self):
        files = list((ROOT / "admin_ai").rglob("*.py")) + [ROOT / "auth_google.py"]
        with_bom = [str(f.relative_to(ROOT)) for f in files if f.read_bytes().startswith(b"\xef\xbb\xbf")]
        self.assertEqual(with_bom, [], "re-save these as UTF-8 without BOM")


if __name__ == "__main__":
    unittest.main()
