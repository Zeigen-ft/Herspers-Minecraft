"""Verify reproducible engine patch staging from inert, checksum-locked archives."""
import difflib
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest


PROJECT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("prepare_upstream", PROJECT / "tools/prepare_upstream.py")
prepare = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prepare)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def diff(before, after, path="src/example.rs", new=False):
    return "".join(difflib.unified_diff(before.decode().splitlines(keepends=True),
                                       after.decode().splitlines(keepends=True),
                                       fromfile="/dev/null" if new else "a/" + path,
                                       tofile="b/" + path)).encode()


class PrepareTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="herspers prepare ")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.archive = self.root / "source.tar.gz"
        self.before = b"one\ntwo\nthree\n"
        self.after = b"one\nTWO\nthree\nfour\n"
        self.lockfile = b"# locked dependencies\nversion = 4\n"
        self.make_archive({"Cargo.lock": self.lockfile, "src/example.rs": self.before})
        self.lock = {"commit": "a" * 40, "archive_root": "engine", "archive_sha256": sha(self.archive.read_bytes())}
        self.patches = self.root / "patches"
        self.patches.mkdir()
        self.patch = self.patches / "example.patch"
        self.patch.write_bytes(diff(self.before, self.after))
        self.manifest = self.patches / "upstream.json"
        self.entry = {"path": "src/example.rs", "before_sha256": sha(self.before),
                      "after_sha256": sha(self.after), "patch": self.patch.name}
        self.write_manifest()
        self.cache = self.root / "prepared"

    def make_archive(self, files):
        with tarfile.open(self.archive, "w:gz") as archive:
            for name, data in files.items():
                member = tarfile.TarInfo("engine/" + name)
                member.size = len(data)
                member.mode = 0o644
                archive.addfile(member, io.BytesIO(data))

    def write_manifest(self, files=None, commit=None):
        self.manifest.write_text(json.dumps({"upstream_commit": commit or self.lock["commit"],
                                             "files": [self.entry] if files is None else files}))

    def stage(self):
        return prepare.prepare(self.lock, self.manifest, self.cache, self.archive)

    def assert_no_temporary_sources(self):
        self.assertFalse(list(self.cache.glob("source-*")))
        self.assertFalse(list(self.cache.glob("*.preparing")))

    def test_reproducible_patch_preserves_archive_and_lockfile(self):
        original_archive = self.archive.read_bytes()
        source = self.stage()
        self.assertEqual((source / self.entry["path"]).read_bytes(), self.after)
        self.assertEqual((source / "Cargo.lock").read_bytes(), self.lockfile)
        self.assertEqual(self.archive.read_bytes(), original_archive)
        stamp = (source / prepare.STAMP).read_bytes()
        self.assertEqual(self.stage(), source)
        self.assertEqual((source / prepare.STAMP).read_bytes(), stamp)
        self.assert_no_temporary_sources()

    def test_ignores_edits_to_fetched_origin_cache(self):
        origin = prepare.fetcher.fetch(self.lock, self.root / "upstream", self.archive)
        (origin / "src/example.rs").write_text("deliberate local edits")
        source = self.stage()
        self.assertEqual((source / "src/example.rs").read_bytes(), self.after)
        self.assertEqual((origin / "src/example.rs").read_text(), "deliberate local edits")

    def test_renamed_archive_same_commit_keeps_old_source_and_provenance(self):
        old_source = self.stage()
        old_stamp = (old_source / prepare.STAMP).read_bytes()
        old_archive = self.archive.read_bytes()
        renamed = self.root / "renamed.tar.gz"
        with tarfile.open(renamed, "w:gz") as archive:
            for name, data in {"Cargo.lock": self.lockfile, "src/example.rs": self.before}.items():
                member = tarfile.TarInfo("renamed/" + name)
                member.size = len(data); member.mode = 0o644
                archive.addfile(member, io.BytesIO(data))
        new_lock = dict(self.lock, archive_root="renamed", archive_sha256=sha(renamed.read_bytes()))
        new_source = prepare.prepare(new_lock, self.manifest, self.cache, renamed)
        self.assertNotEqual(new_source, old_source)
        self.assertEqual((new_source / "src/example.rs").read_bytes(), self.after)
        self.assertEqual((old_source / "src/example.rs").read_bytes(), self.after)
        self.assertEqual((old_source / prepare.STAMP).read_bytes(), old_stamp)
        self.assertEqual(self.archive.read_bytes(), old_archive)
        self.assertEqual(prepare.tree_digest(new_source), prepare.tree_digest(old_source))
        self.assert_no_temporary_sources()

    def test_invalid_archive_identity_is_rejected_before_cache_creation(self):
        self.lock["archive_sha256"] = "../escape"
        with self.assertRaisesRegex(ValueError, "archive checksum"):
            self.stage()
        self.assertFalse(self.cache.exists())

    def test_new_file_patch(self):
        self.entry.update(path="src/new.rs", before_sha256=None, after_sha256=sha(b"new code\n"))
        self.patch.write_bytes(diff(b"", b"new code\n", self.entry["path"], new=True))
        self.write_manifest()
        source = self.stage()
        self.assertEqual((source / "src/new.rs").read_bytes(), b"new code\n")
        self.assertEqual((source / "src/example.rs").read_bytes(), self.before)

    def test_no_files_still_returns_pristine_source(self):
        self.write_manifest(files=[])
        source = self.stage()
        self.assertEqual((source / "src/example.rs").read_bytes(), self.before)

    def test_changed_patch_selects_new_cache_without_changing_old(self):
        old_source = self.stage()
        old_stamp = (old_source / prepare.STAMP).read_bytes()
        self.after += b"another line\n"
        self.patch.write_bytes(diff(self.before, self.after))
        self.entry["after_sha256"] = sha(self.after)
        self.write_manifest()
        new_source = self.stage()
        self.assertNotEqual(old_source, new_source)
        self.assertEqual((old_source / prepare.STAMP).read_bytes(), old_stamp)
        self.assertEqual((old_source / "src/example.rs").read_bytes(), b"one\nTWO\nthree\nfour\n")
        self.assertEqual((new_source / "src/example.rs").read_bytes(), self.after)

    def test_edited_prepared_cache_is_refused_and_preserved(self):
        source = self.stage()
        (source / "src/example.rs").write_text("keep my edits")
        with self.assertRaisesRegex(ValueError, "preserve"):
            self.stage()
        self.assertEqual((source / "src/example.rs").read_text(), "keep my edits")
        self.assert_no_temporary_sources()

    def test_extra_prepared_cache_file_is_not_silently_trusted(self):
        source = self.stage()
        (source / "untracked.rs").write_text("keep this")
        with self.assertRaisesRegex(ValueError, "preserve"):
            self.stage()
        self.assertEqual((source / "untracked.rs").read_text(), "keep this")

    def test_unknown_cache_stamp_is_preserved(self):
        source = self.stage()
        stamp = source / prepare.STAMP
        stamp.write_text('{"unknown": true}')
        with self.assertRaisesRegex(ValueError, "preserve"):
            self.stage()
        self.assertEqual(stamp.read_text(), '{"unknown": true}')

    def test_archive_checksum_failure_prevents_preparation(self):
        self.lock["archive_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "checksum"):
            self.stage()
        self.assertFalse(self.cache.exists())

    def test_preimage_and_postimage_hashes_are_required(self):
        for field in ("before_sha256", "after_sha256"):
            original = self.entry[field]
            self.entry[field] = "0" * 64
            self.write_manifest()
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "checksum mismatch"):
                self.stage()
            self.assert_no_temporary_sources()
            self.entry[field] = original

    def test_stale_hunk_context_is_refused(self):
        self.patch.write_bytes(self.patch.read_bytes().replace(b"-two\n", b"-stale\n"))
        with self.assertRaisesRegex(ValueError, "context mismatch"):
            self.stage()
        self.assert_no_temporary_sources()

    def test_missing_manifest_and_wrong_commit_are_refused(self):
        self.manifest.unlink()
        with self.assertRaisesRegex(ValueError, "Missing regular file"):
            self.stage()
        self.write_manifest(commit="b" * 40)
        with self.assertRaisesRegex(ValueError, "pinned upstream commit"):
            self.stage()

    def test_unsafe_target_or_patch_paths_are_refused(self):
        for field in ("path", "patch"):
            original = self.entry[field]
            for path in ("../escape", "/absolute", "a/../escape", "C:/escape", "a\\escape", "con", "a/b."):
                self.entry[field] = path
                self.write_manifest()
                with self.subTest(field=field, path=path), self.assertRaisesRegex(ValueError, "Unsafe"):
                    self.stage()
            self.entry[field] = original

    def test_duplicate_and_lockfile_patches_are_refused(self):
        self.write_manifest(files=[self.entry, self.entry])
        with self.assertRaisesRegex(ValueError, "Duplicate or protected"):
            self.stage()
        self.entry["path"] = "Cargo.lock"
        self.write_manifest()
        with self.assertRaisesRegex(ValueError, "Duplicate or protected"):
            self.stage()

    def test_patch_symlink_is_refused(self):
        real_patch = self.patches / "real.patch"
        self.patch.rename(real_patch)
        try:
            self.patch.symlink_to(real_patch)
        except OSError:
            self.skipTest("Symlinks are unavailable")
        with self.assertRaisesRegex(ValueError, "Symlink"):
            self.stage()

    def test_prepared_cache_symlink_is_refused_without_touching_target(self):
        source = self.stage()
        saved = self.root / "saved"
        source.rename(saved)
        try:
            source.symlink_to(saved, target_is_directory=True)
        except OSError:
            self.skipTest("Symlinks are unavailable")
        stamp = (saved / prepare.STAMP).read_bytes()
        with self.assertRaisesRegex(ValueError, "preserve"):
            self.stage()
        self.assertEqual((saved / prepare.STAMP).read_bytes(), stamp)

    def test_symlinked_cache_parent_is_refused(self):
        elsewhere = self.root / "elsewhere"
        elsewhere.mkdir()
        link = self.root / "redirect"
        try:
            link.symlink_to(elsewhere, target_is_directory=True)
        except OSError:
            self.skipTest("Symlinks are unavailable")
        self.cache = link / "prepared"
        with self.assertRaisesRegex(ValueError, "Symlink"):
            self.stage()
        self.assertFalse(list(elsewhere.iterdir()))


class UnifiedPatchTests(unittest.TestCase):
    def test_multiple_hunks_and_exact_offsets(self):
        original = b"".join(f"line {n}\n".encode() for n in range(20))
        revised = original.replace(b"line 1\n", b"replacement\nextra\n").replace(b"line 18\n", b"")
        patch = diff(original, revised)
        self.assertEqual(prepare.apply_patch(original, patch, "src/example.rs"), revised)
        with self.assertRaisesRegex(ValueError, "output position mismatch"):
            prepare.apply_patch(b"a\n", b"--- a/x\n+++ b/x\n@@ -1 +2 @@\n-a\n+b\n", "x")

    def test_crlf_and_no_final_newline_are_preserved(self):
        original, revised = b"first\r\nsecond\r\n", b"first\r\nSECOND\r\n"
        self.assertEqual(prepare.apply_patch(original, diff(original, revised, "x"), "x"), revised)
        patch = b"--- a/x\n+++ b/x\n@@ -1 +1 @@\n-old\n\\ No newline at end of file\n+new\n\\ No newline at end of file\n"
        self.assertEqual(prepare.apply_patch(b"old", patch, "x"), b"new")

    def test_insertion_and_deletion_only_hunks(self):
        for original, revised in ((b"a\n", b"a\nb\n"), (b"a\nb\n", b"b\n"), (b"a\n", b"")):
            with self.subTest(original=original):
                self.assertEqual(prepare.apply_patch(original, diff(original, revised, "x"), "x"), revised)

    def test_headers_and_hunk_lengths_are_strict(self):
        for patch in (b"--- a/wrong\n+++ b/x\n@@ -1 +1 @@\n-a\n+b\n",
                      b"--- a/x\n+++ b/x\n@@ -1,2 +1 @@\n-a\n+b\n",
                      b"--- a/x\n+++ b/x\n"):
            with self.subTest(patch=patch), self.assertRaises(ValueError):
                prepare.apply_patch(b"a\n", patch, "x")


if __name__ == "__main__":
    unittest.main()
