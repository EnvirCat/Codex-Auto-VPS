import unittest

from scripts.install_traffic_meter import InstallError, rewrite_caddyfile


SAMPLE_CADDYFILE = '''{
    auto_https disable_redirects
}

https://sub.example.invalid:9443 {
    bind 127.0.0.1
    @clash path /private/opaque-token/clash.yaml
    handle @clash {
        header {
            Cache-Control "no-store"
            Profile-Title "base64:YWJj"
        }
        root * /srv/subscriptions
        file_server
    }
    @hiddify path /private/opaque-token/hiddify.txt
    handle @hiddify {
        header {
            Cache-Control "no-store"
        }
        root * /srv/subscriptions
        file_server
    }
    respond 404
}
'''


class InstallerRewriteTests(unittest.TestCase):
    def test_rewrites_only_the_two_exact_subscription_handlers(self):
        changed, root, allowed = rewrite_caddyfile(SAMPLE_CADDYFILE, "127.0.0.1", 19087)
        self.assertEqual(root.as_posix(), "/srv/subscriptions")
        self.assertEqual(
            allowed,
            frozenset(
                {
                    "/private/opaque-token/clash.yaml",
                    "/private/opaque-token/hiddify.txt",
                }
            ),
        )
        self.assertEqual(changed.count("reverse_proxy 127.0.0.1:19087"), 2)
        self.assertNotIn("file_server", changed)
        self.assertIn('Profile-Title "base64:YWJj"', changed)
        self.assertIn("respond 404", changed)

    def test_refuses_paths_that_do_not_share_one_private_directory(self):
        changed = SAMPLE_CADDYFILE.replace(
            "/private/opaque-token/hiddify.txt", "/other/path/hiddify.txt"
        )
        with self.assertRaises(InstallError):
            rewrite_caddyfile(changed, "127.0.0.1", 19087)

    def test_refuses_wildcard_routes(self):
        changed = SAMPLE_CADDYFILE.replace(
            "/private/opaque-token/clash.yaml", "/private/opaque-token/*"
        )
        with self.assertRaises(InstallError):
            rewrite_caddyfile(changed, "127.0.0.1", 19087)


if __name__ == "__main__":
    unittest.main()
