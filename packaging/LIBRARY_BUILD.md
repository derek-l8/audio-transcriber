# Library sources and rebuilds

The Windows app uses unmodified PyPI wheels for PySide6/Shiboken 6.11.2 and
Qt 6.11.2. `third-party-sources.json` lists the upstream archives and SHA-256
hashes. The release's `npu-scribe-0.1.0-library-sources.zip` contains those
archives, this guide, and notices. Qt DLLs and plugins remain separate files;
compatible rebuilt libraries can replace them in `_internal/PySide6/`.
Replace Shiboken in `_internal/shiboken6/`. Close the app before replacing files.
Keep a backup of the original bundle. No signature check prevents replacements.

## Qt and PySide

Extract the Qt module archives side by side into a Qt source folder. With a
Windows x64 MSVC 2022 developer shell, CMake and Ninja, build Qt Base first.
The example assumes the extracted Qt Base source is in `C:\Qt\src`:

```powershell
New-Item -ItemType Directory -Force C:\Qt\build-base | Out-Null
Set-Location C:\Qt\build-base
C:\Qt\src\qtbase-everywhere-src-6.11.2\configure.bat -prefix C:\Qt\custom -release -shared -opensource -confirm-license -nomake examples -nomake tests
cmake --build . --parallel
cmake --install .
```

Then build the supplied add-on modules with
`C:\Qt\custom\bin\qt-configure-module.bat SOURCE_FOLDER`, followed by the
same CMake build/install commands. Build Qt Multimedia against the FFmpeg
libraries described below. Build PySide/Shiboken from the supplied pyside-setup
archive with Python 3.12, the rebuilt Qt's qtpaths, and its documented LLVM/Clang
prerequisites:

```powershell
python setup.py bdist_wheel --qtpaths=C:\Qt\custom\bin\qtpaths.exe --parallel=4
```

The archives include the detailed build documentation. The Qt build-recipes
archive contains upstream provisioning scripts and compiler configurations.
These are rebuild instructions; we have not rebuilt the upstream wheels locally.

## FFmpeg and zlib

The playback DLLs report FFmpeg 7.1.5. Qt's v6.11.2 Windows provisioning recipe
uses the unmodified upstream n7.1.5 archive (SHA-1
`2322a4cef2d607c7f0048953662ec5e27c587ae8`). That matches the included archive.
The recipe and `ffmpeg_config_options.txt` are inside the Qt build-recipes
archive under `coin/provisioning/common/`.

The binary reports this configuration:

```text
--prefix=/c/FFmpeg-n7.1.5/build/msvc/installed --disable-programs --disable-doc --disable-debug --enable-network --disable-lzma --enable-pic --disable-vulkan --disable-v4l2-m2m --disable-decoder=truemotion1 --disable-avdevice --disable-avfilter --enable-zlib --extra-cflags='-IC:/zlib-1.3.1/build/amd64' --extra-ldflags='-LIBPATH:C:/zlib-1.3.1/build/amd64' --toolchain=msvc --enable-shared --disable-static
```

Use an MSVC x64 developer shell, MSYS2, Make and NASM. Run configure from a
separate FFmpeg build directory, adjusting the prefix and zlib paths, then
`make -j4 install`. Qt's `windows/zlib.ps1` builds zlib 1.3.1 and applies two
build fixes: remove the unistd.h include from zconf.h and the fixed DLL base
address from win32/Makefile.msc. Both fixes and their build commands are supplied
in that recipe. No local FFmpeg patches were made.

Qt Multimedia's attribution metadata still names FFmpeg 7.1.3. The source
selection here follows the DLL's reported version/configuration and the
versioned provisioning recipe, which both identify 7.1.5.

Qt/PySide are used under LGPLv3 and FFmpeg under LGPLv2.1 or later. Their source
archives contain their licenses and third-party notices. You may modify the
libraries and reverse-engineer the app to debug those modifications. NPU Scribe's
own source and packaging recipe are available in the same release and repository.
