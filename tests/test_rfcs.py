import importlib.util
from pathlib import Path
import shutil
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('rfcs', SOURCE / 'scripts/rfcs.py')
rfcs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rfcs)


class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'repository'
        shutil.copytree(SOURCE, self.root, ignore=shutil.ignore_patterns('.git', '__pycache__'))

    def new(self, slug='example'):
        return rfcs.create(self.root, slug, 'Example feature', '@author', 'language')

    def change(self, path, field, value):
        text = path.read_text()
        import re
        text, count = re.subn(rf'^\| {re.escape(field)} \| [^|\n]* \|$', f'| {field} | {value} |', text, flags=re.M)
        self.assertEqual(count, 1)
        path.write_text(text)

    def test_empty_catalog_and_new_draft(self):
        self.assertEqual(rfcs.check(self.root), 0)
        first = self.new()
        second = self.new('second')
        self.assertEqual(first.name, '0001-example.md')
        self.assertEqual(second.name, '0002-second.md')
        self.assertEqual(rfcs.check(self.root), 2)
        self.assertNotIn('{{', first.read_text())

    def test_stale_index_is_rejected(self):
        path = self.new()
        self.change(path, 'Status', 'deferred')
        with self.assertRaisesRegex(rfcs.Invalid, 'index is stale'):
            rfcs.check(self.root)

    def test_duplicate_number_is_rejected(self):
        path = self.new()
        shutil.copyfile(path, path.with_name('0001-other.md'))
        with self.assertRaisesRegex(rfcs.Invalid, 'Duplicate RFC number'):
            rfcs.catalog(self.root)

    def test_accepted_requires_proposal_and_decision(self):
        path = self.new()
        self.change(path, 'Status', 'accepted')
        with self.assertRaisesRegex(rfcs.Invalid, 'proposal PR link'):
            rfcs.read_rfc(path)
        self.change(path, 'Proposal', rfcs.REPO + 'pull/12')
        with self.assertRaisesRegex(rfcs.Invalid, 'decision link'):
            rfcs.read_rfc(path)
        self.change(path, 'Decision', rfcs.REPO + 'pull/12#issuecomment-123')
        self.assertEqual(rfcs.read_rfc(path)['Status'], 'accepted')

    def test_implemented_requires_implementation(self):
        path = self.new()
        for field, value in [('Status', 'implemented'), ('Proposal', rfcs.REPO + 'pull/12'), ('Decision', rfcs.REPO + 'pull/12#issuecomment-123')]:
            self.change(path, field, value)
        with self.assertRaisesRegex(rfcs.Invalid, 'landed implementation'):
            rfcs.read_rfc(path)
        self.change(path, 'Implementation', 'https://github.com/lang-gti-official/gti/pull/250')
        self.assertEqual(rfcs.read_rfc(path)['Status'], 'implemented')

    def test_unknown_status_and_invalid_date(self):
        path = self.new()
        self.change(path, 'Status', 'approved-ish')
        with self.assertRaisesRegex(rfcs.Invalid, 'unknown status'):
            rfcs.read_rfc(path)
        self.change(path, 'Status', 'draft')
        self.change(path, 'Created', '2026-02-31')
        with self.assertRaisesRegex(rfcs.Invalid, 'valid ISO dates'):
            rfcs.read_rfc(path)

    def test_missing_sections_and_duplicate_fields(self):
        path = self.new()
        original = path.read_text()
        path.write_text(original.replace('## Safety and correctness', '## Safety renamed'))
        with self.assertRaisesRegex(rfcs.Invalid, 'Safety and correctness'):
            rfcs.read_rfc(path)
        path.write_text(original.replace('| Status | draft |', '| Status | draft |\n| Status | review |'))
        with self.assertRaisesRegex(rfcs.Invalid, 'duplicate metadata'):
            rfcs.read_rfc(path)

    def test_supersession_requires_existing_reciprocal_reference(self):
        old = self.new()
        new = self.new('replacement')
        for field, value in [('Status', 'superseded'), ('Proposal', rfcs.REPO + 'pull/1'), ('Decision', rfcs.REPO + 'pull/2'), ('Superseded by', '0002')]:
            self.change(old, field, value)
        with self.assertRaisesRegex(rfcs.Invalid, 'link back'):
            rfcs.catalog(self.root)
        self.change(new, 'Supersedes', '0001')
        self.assertEqual(len(rfcs.catalog(self.root)), 2)
        self.change(new, 'Supersedes', '0099')
        with self.assertRaisesRegex(rfcs.Invalid, 'invalid Supersedes'):
            rfcs.catalog(self.root)

    def test_broken_and_escaping_local_links(self):
        path = self.new()
        for target in ['missing.md', '../../outside.md']:
            with self.subTest(target=target):
                original = path.read_text()
                path.write_text(original + f'\n[Reference]({target})\n')
                with self.assertRaisesRegex(rfcs.Invalid, 'broken local file link'):
                    rfcs.local_links(self.root)
                path.write_text(original)

    def test_invalid_inputs_cannot_escape_the_rfc_directory(self):
        with self.assertRaisesRegex(rfcs.Invalid, 'slug'):
            self.new('../outside')
        with self.assertRaisesRegex(rfcs.Invalid, 'single-line'):
            rfcs.create(self.root, 'example', 'Title\n| Status | accepted |', '@author', 'language')
        self.assertEqual(rfcs.check(self.root), 0)


if __name__ == '__main__':
    unittest.main()
