#!/usr/bin/env python3
"""Keep unpublished downloads out of the production documentation."""
import copy
import io
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import published_release as publication


class PublicationTests(unittest.TestCase):
    def setUp(self):
        self.release = dict(tag_name='v9.8.7', draft=False, prerelease=False,
                            published_at='2026-10-14T00:00:00Z', assets=[
            dict(name=name, state='uploaded', size=100) for name in [
                'curlimp-9.8.7-linux-amd64.tar.gz', 'curlimp-9.8.7-linux-arm64.tar.gz',
                'curlimp-9.8.7-macos-arm64.tar.gz', 'SHA256SUMS']])
        self.image = dict(name='9.8.7', tag_status='active', images=[
            dict(os='linux', architecture=arch, status='active', digest='sha256:' + 'a' * 64)
            for arch in ['amd64', 'arm64']])

    def test_accepts_complete_stable_release(self):
        self.assertTrue(publication.eligible('9.8.7', self.release, self.image)[0])

    def test_rejects_unpublished_or_wrong_release(self):
        for release in [None, dict(self.release, draft=True), dict(self.release, prerelease=True),
                        dict(self.release, published_at=None), dict(self.release, tag_name='v9.8.6')]:
            with self.subTest(release=release):
                self.assertFalse(publication.eligible('9.8.7', release, self.image)[0])
        self.assertFalse(publication.eligible('9.8.7-rc.1', self.release, self.image)[0])

    def test_requires_every_uploaded_nonempty_asset(self):
        for index in range(4):
            for field, value in [('size', 0), ('state', 'new'), ('name', 'unrelated')]:
                release = copy.deepcopy(self.release)
                release['assets'][index][field] = value
                with self.subTest(index=index, field=field):
                    self.assertFalse(publication.eligible('9.8.7', release, self.image)[0])

    def test_requires_both_published_linux_images(self):
        for image in [None, dict(self.image, images=self.image['images'][:1]),
                      dict(self.image, name='9.8.6'), dict(self.image, tag_status='inactive')]:
            with self.subTest(image=image):
                self.assertFalse(publication.eligible('9.8.7', self.release, image)[0])
        for field, value in [('os', 'windows'), ('status', 'inactive'), ('digest', '')]:
            image = copy.deepcopy(self.image)
            image['images'][1][field] = value
            self.assertFalse(publication.eligible('9.8.7', self.release, image)[0])

    def test_only_http_404_means_not_published(self):
        for status in [404, 401, 403, 429, 500, 503]:
            error = HTTPError('https://api.github.com/test', status, 'test', {}, io.BytesIO())
            self.addCleanup(error.close)
            with self.subTest(status=status), patch.object(publication, 'urlopen', side_effect=error):
                if status == 404:
                    self.assertIsNone(publication.fetch_json('https://api.github.com/test'))
                else:
                    with self.assertRaises(HTTPError):
                        publication.fetch_json('https://api.github.com/test')


if __name__ == '__main__':
    unittest.main()
