from conans import ConanFile, tools, Meson, VisualStudioBuildEnvironment
import glob
import os
import shutil

_meson_feature = ["disabled", "enabled", "auto"]
_features = ['ximagesrc', 'ximagesrc-xshm', 'ximagesrc-xfixes', 'ximagesrc-xdamage', 'multifile']

class GStPluginsGoodConan(ConanFile):
    """
    Copied and adapted from bincrafters/gst-plugins-base
    """
    name = "gst-plugins-good"
    version = "1.16.2"
    description = "GStreamer is a development framework for creating applications like media players, video editors, " \
                  "streaming media broadcasters and so on"
    topics = ("conan", "gstreamer", "multimedia", "video", "audio", "broadcasting", "framework", "media")
    homepage = "https://gstreamer.freedesktop.org/"
    license = "GPL-2.0-only"
    exports = ["LICENSE.md"]
    settings = "os", "arch", "compiler", "build_type"
    options = dict({"shared": [True, False], "fPIC": [True, False]}, **{f: _meson_feature for f in _features})
    default_options = dict({"shared": False, "fPIC": True}, **{f: "auto" for f in _features})
    _source_subfolder = "source_subfolder"
    _build_subfolder = "build_subfolder"
    exports_sources = ["patches/*.patch"]

    requires = ("gst-plugins-base/1.16.0@bincrafters/stable",)
    generators = "pkg_config"

    @property
    def _is_msvc(self):
        return self.settings.compiler == "Visual Studio"

    def configure(self):
        del self.settings.compiler.libcxx
        del self.settings.compiler.cppstd
        self.options['gstreamer'].shared = self.options.shared

    def config_options(self):
        if self.settings.os == 'Windows':
            del self.options.fPIC

    @property
    def _meson_required(self):
        from six import StringIO
        mybuf = StringIO()
        if self.run("meson -v", output=mybuf, ignore_errors=True) != 0:
            return True
        return tools.Version(mybuf.getvalue()) < tools.Version('0.53.0')

    def build_requirements(self):
        if self._meson_required:
            self.build_requires("meson/0.53.0")
        if not tools.which("pkg-config"):
            self.build_requires("pkg-config_installer/0.29.2@bincrafters/stable")
        self.build_requires("bison_installer/3.3.2@bincrafters/stable")
        self.build_requires("flex_installer/2.6.4@bincrafters/stable")

    def source(self):
        source_url = "https://gstreamer.freedesktop.org/src/{n}/{n}-{v}.tar.xz".format(v=self.version, n=self.name)
        sha256 = "40bb3bafda25c0b739c8fc36e48380fccf61c4d3f83747e97ac3f9b0171b1319"
        tools.get(source_url, sha256=sha256)
        os.rename("%s-%s" % (self.name, self.version), self._source_subfolder)

    def _apply_patches(self):
        for filename in sorted(glob.glob("patches/*.patch")):
            self.output.info('applying patch "%s"' % filename)
            tools.patch(base_path=self._source_subfolder, patch_file=filename)

    def _configure_meson(self):
        defs = dict()

        def add_flag(name, value):
            if name in defs:
                defs[name] += " " + value
            else:
                defs[name] = value

        def add_compiler_flag(value):
            add_flag("c_args", value)
            add_flag("cpp_args", value)

        def add_linker_flag(value):
            add_flag("c_link_args", value)
            add_flag("cpp_link_args", value)

        meson = Meson(self)
        if self.settings.compiler == "Visual Studio":
            add_linker_flag("-lws2_32")
            add_compiler_flag("-%s" % self.settings.compiler.runtime)
            if int(str(self.settings.compiler.version)) < 14:
                add_compiler_flag("-Dsnprintf=_snprintf")
        if self.settings.get_safe("compiler.runtime"):
            defs["b_vscrt"] = str(self.settings.compiler.runtime).lower()
        for x in ["tools", "examples", "benchmarks", "tests"]:
            defs[x] = "disabled"
        for x in _features:
            defs[x] = self.options.get_safe(x)
        meson.configure(build_folder=self._build_subfolder,
                        source_folder=self._source_subfolder,
                        defs=defs)
        return meson

    def _copy_pkg_config(self, name):
        root = self.deps_cpp_info[name].rootpath
        pc_dir = os.path.join(root, 'lib', 'pkgconfig')
        pc_files = glob.glob('%s/*.pc' % pc_dir)
        if not pc_files:  # zlib store .pc in root
            pc_files = glob.glob('%s/*.pc' % root)
        for pc_name in pc_files:
            new_pc = os.path.basename(pc_name)
            self.output.warn('copy .pc file %s' % os.path.basename(pc_name))
            shutil.copy(pc_name, new_pc)
            prefix = tools.unix_path(root) if self.settings.os == 'Windows' else root
            tools.replace_prefix_in_pc_file(new_pc, prefix)

    def build(self):
        self._apply_patches()
        self._copy_pkg_config("glib")
        self._copy_pkg_config("gstreamer")
        self._copy_pkg_config("gst-plugins-base")
        with tools.environment_append(VisualStudioBuildEnvironment(self).vars) if self._is_msvc else tools.no_op():
            meson = self._configure_meson()
            meson.build()

    def _fix_library_names(self, path):
        # regression in 1.16
        if self.settings.compiler == "Visual Studio":
            with tools.chdir(path):
                for filename_old in glob.glob("*.a"):
                    filename_new = filename_old[3:-2] + ".lib"
                    self.output.info("rename %s into %s" % (filename_old, filename_new))
                    shutil.move(filename_old, filename_new)

    def package(self):
        self.copy(pattern="LICENSE", dst="licenses", src=self._source_subfolder)
        with tools.environment_append(VisualStudioBuildEnvironment(self).vars) if self._is_msvc else tools.no_op():
            meson = self._configure_meson()
            meson.install()

        self._fix_library_names(os.path.join(self.package_folder, "lib"))
        self._fix_library_names(os.path.join(self.package_folder, "lib", "gstreamer-1.0"))

    def package_info(self):
        gst_plugin_path = os.path.join(self.package_folder, "lib", "gstreamer-1.0")
        if self.options.shared:
            self.output.info("Appending GST_PLUGIN_PATH env var : %s" % gst_plugin_path)
            self.env_info.GST_PLUGIN_PATH.append(gst_plugin_path)
        else:
            self.cpp_info.defines.append("GST_PLUGINS_BASE_STATIC")
            self.cpp_info.libdirs.append(gst_plugin_path)
            self.cpp_info.libs.extend(["gstaudiotestsrc",
                                       "gstaudioconvert",
                                       "gstaudiomixer",
                                       "gstaudiorate",
                                       "gstaudioresample",
                                       "gstvideotestsrc",
                                       "gstvideoconvert",
                                       "gstvideorate",
                                       "gstvideoscale",
                                       "gstadder",
                                       "gstapp",
                                       "gstcompositor",
                                       "gstencoding",
                                       "gstgio",
                                       "gstopengl",
                                       "gstoverlaycomposition",
                                       "gstpbtypes",
                                       "gstplayback",
                                       "gstrawparse",
                                       "gstsubparse",
                                       "gsttcp",
                                       "gsttypefindfunctions",
                                       "gstvolume"])
            if self.settings.os == "Linux":
                self.cpp_info.libs.remove("gstopengl")
        self.cpp_info.libs.extend(["gstallocators-1.0",
                                   "gstapp-1.0",
                                   "gstaudio-1.0",
                                   "gstfft-1.0",
                                   "gstpbutils-1.0",
                                   "gstriff-1.0",
                                   "gstrtp-1.0",
                                   "gstrtsp-1.0",
                                   "gstsdp-1.0",
                                   "gsttag-1.0",
                                   "gstvideo-1.0",
                                   "gstgl-1.0"])
        if self.settings.os == "Linux":
            self.cpp_info.libs.remove("gstgl-1.0")
        self.cpp_info.includedirs = ["include", os.path.join("include", "gstreamer-1.0")]
