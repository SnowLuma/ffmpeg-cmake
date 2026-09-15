"""Regression tests for dependency closure and actual upstream source selection."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("ffconfigure", ROOT / "tools/configure.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class MetadataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.meta = module.Metadata(ROOT / "ffmpeg")

    def resolver(self, roots, blocked=(), **facts):
        facts = {"gpl": False, "zlib": True, "avutil": True, "avcodec": True,
                 "avformat": True, "avfilter": True, "swresample": True,
                 "swscale": True, "threads": True, **facts}
        result = module.Resolver(self.meta, facts, set(blocked), roots)
        for root in roots:
            result.enable(root)
        return result

    def test_all_registry_families_are_discovered(self):
        for kind, group in self.meta.groups.items():
            self.assertTrue(group, kind)
        self.assertIn("h264_d3d11va_hwaccel", self.meta.groups["hwaccel"])

    def test_decoder_dependency_closure(self):
        result = self.resolver(["hevc_decoder"])
        self.assertTrue({"hevc_decoder", "cabac", "golomb", "hevcparse", "hevc_sei", "videodsp"} <= result.active)
        self.assertNotIn("mpeg4_decoder", result.active)

    def test_missing_transitive_dependency_disables_codec(self):
        result = self.resolver(["png_decoder"], zlib=False)
        self.assertNotIn("png_decoder", result.active)
        self.assertIn("inflate_wrapper", result.reason["png_decoder"])

    def test_gpl_dependency(self):
        self.assertNotIn("boxblur_filter", self.resolver(["boxblur_filter"]).active)
        self.assertIn("boxblur_filter", self.resolver(["boxblur_filter"], gpl=True).active)

    def test_config_extra_does_not_enable_unprobed_external_capabilities(self):
        result = self.resolver(["libx262_encoder", "mestimate_d3d12_filter"], d3d12va=True, id3d12videomotionestimator=True)
        self.assertNotIn("libx262_encoder", result.active)
        self.assertNotIn("mestimate_d3d12_filter", result.active)

    def test_hard_disabled_dependency_is_not_reenabled(self):
        result = self.resolver(["h264_decoder"], blocked=["golomb"])
        self.assertNotIn("h264_decoder", result.active)

    def test_unknown_component_rejected(self):
        with self.assertRaisesRegex(ValueError, "Unknown decoder"):
            module.parse_selections(self.meta, {"profile": "minimal", "components": {"decoder": "h265_typo"}})

    def test_minimal_and_full_are_distinct(self):
        roots, _ = module.parse_selections(self.meta, {"profile": "minimal", "components": {}})
        self.assertFalse(roots)
        roots, _ = module.parse_selections(self.meta, {"profile": "full", "components": {}})
        self.assertEqual(roots, set(self.meta.components))

    def test_make_conditions_and_nested_object_lists(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp)
            (source / "Makefile").write_text("OBJS = base.o\nOBJS-$(CONFIG_FOO) += foo.o \\\n more.o\nOBJS-$(!CONFIG_BAR) += fallback.o\nifdef CONFIG_BAR\nOBJS += bad.o\nelse\nOBJS += good.o\nendif\nOBJS += $(if $(!CONFIG_BAR), conditional.o)\n")
            lists = module.ObjectLists(source, {"CONFIG_FOO": 1, "CONFIG_BAR": 0}, "x86")
            lists.read(source / "Makefile")
            self.assertEqual(set(lists.values("OBJS")), {"base.o", "foo.o", "more.o", "fallback.o", "good.o", "conditional.o"})

    def test_aac_runtime_table_source_is_preserved(self):
        lists = module.ObjectLists(ROOT / "ffmpeg", {"CONFIG_AAC_DECODER": 1, "CONFIG_HARDCODED_TABLES": 0}, "x86")
        lists.read(ROOT / "ffmpeg/libavcodec/Makefile")
        self.assertIn("cbrt_tablegen_common.o", lists.values("OBJS"))

    def test_tls_backend_sources_are_preserved(self):
        lists = module.ObjectLists(ROOT / "ffmpeg", {"CONFIG_TLS_PROTOCOL": 1, "CONFIG_SCHANNEL": 1}, "x86")
        lists.read(ROOT / "ffmpeg/libavformat/Makefile")
        self.assertIn("tls_schannel.o", lists.values("OBJS"))

    def test_unhandled_source_variable_fails_instead_of_dropping_sources(self):
        lists = module.ObjectLists(ROOT / "ffmpeg", {}, "x86")
        lists.vars["OBJS"] = "base.o $(NEW_UPSTREAM_SOURCE_LIST)"
        with self.assertRaisesRegex(ValueError, "Unknown variable"):
            lists.values("OBJS")



if __name__ == "__main__":
    unittest.main()
