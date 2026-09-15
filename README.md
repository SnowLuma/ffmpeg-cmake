# FFmpeg CMake

[![Build](https://github.com/SnowLuma/ffmpeg-cmake/actions/workflows/build.yml/badge.svg)](https://github.com/SnowLuma/ffmpeg-cmake/actions/workflows/build.yml)

FFmpeg 的原生 CMake 构建系统，支持 Windows、Linux 和 macOS。使用 CMake、Ninja 和 Python 标准库，不执行上游 `configure` 或 Makefile，无需 MSYS2、Cygwin 或 autotools。

- 默认 `full`，启用当前平台和依赖条件下可用的组件，不按场景裁剪。
- 支持七个 FFmpeg 库、`ffmpeg`、`ffprobe`，安装 SDL2 后支持 `ffplay`。
- 支持组件白名单、依赖自动补齐、静态库和动态库。
- 支持外部库源码构建、平台检测缓存、依赖二进制缓存和 sccache 编译缓存。

## 环境要求

公共依赖：CMake 3.25+、Ninja、Python 3.10+、Git。x64 汇编优化需要 NASM；ARM64 使用编译器自带汇编器。

| 平台 | 工具链 | 默认预设 |
| --- | --- | --- |
| Windows x64 | Visual Studio 2022 C++ Build Tools，包含 Windows SDK、CMake 和 Ninja | `windows-msvc` |
| Linux x64 / ARM64 | GCC 或 Clang | `linux` |
| macOS Intel / Apple Silicon | Xcode Command Line Tools / AppleClang | `macos` |

Windows 可使用 LLVM / clang-cl，选择 `windows` 或 `windows-shared` 预设。

## 快速开始

### 获取工程与源码

```sh
git clone https://github.com/SnowLuma/ffmpeg-cmake.git
cd ffmpeg-cmake
python tools/sources.py --branch master
```

`ffmpeg/` 已加入 Git ignore，由 Python 脚本管理，不使用子模块。省略源码获取步骤时，构建入口会自动拉取 `master`；已有源码不会自动更新。

```sh
# 更新或切换分支
python tools/sources.py --branch release/8.0

# 固定提交；将 <commit> 替换为对应的提交 SHA
python tools/sources.py --branch master --revision <commit>
```

### Windows

在普通 PowerShell 中执行，入口会初始化 Visual Studio 编译环境：

```powershell
./build.ps1 -Bootstrap -Action Test
./build.ps1 -Action Install
```

`-Bootstrap` 将固定版本 NASM 和 sccache 安装到项目的 `.tools/bin`，无需管理员权限。已安装这两个工具时可省略。

### Linux

以 Ubuntu / Debian 为例，安装基础工具及可选的系统开发库：

```sh
sudo apt-get install build-essential cmake ninja-build python3 git nasm zlib1g-dev libbz2-dev liblzma-dev libasound2-dev libsdl2-dev
python3 build.py --action test
python3 build.py --action install
```

### macOS

安装 Xcode Command Line Tools 后，通过 Homebrew 安装构建工具：

```sh
brew install cmake ninja python nasm sccache sdl2
python3 build.py --action test
python3 build.py --action install
```

### 构建入口

`build.py` 默认使用当前平台预设，支持 `configure`、`build`、`test`、`install`，默认动作为 `build`。后三项都会先配置并编译。

```sh
python build.py --jobs 8
python build.py --action test -- -DBUILD_SHARED_LIBS=ON
```

额外 CMake 参数放在 `--` 后。程序输出到 `build/<preset>/bin`，库输出到 `build/<preset>/lib`，安装目录为 `install/<preset>`。

也可直接运行 CMake；Windows 需先打开 Developer PowerShell：

```sh
cmake --preset windows-msvc
cmake --build --preset windows-msvc --parallel
ctest --preset windows-msvc
cmake --install build/windows-msvc
```

## 按需裁剪

默认无需指定裁剪参数。`full` 会根据平台 API、外部依赖和许可开关选择可用组件；GPL 和 version3 默认均关闭。

### 从最小集合开始

`minimal` 预设关闭命令行程序，以空的可选组件集合为起点。以下示例保留 H.264、HEVC、AAC 解码，以及 MP4/MOV、Matroska 文件读取：

```sh
python build.py --preset minimal -- "-DFFMPEG_DECODERS=h264;hevc;aac" "-DFFMPEG_DEMUXERS=mov;matroska" "-DFFMPEG_PARSERS=h264;hevc;aac" -DFFMPEG_PROTOCOLS=file
```

最小预设仍构建七个库的基础 API。可继续关闭不需要的库，例如：

```sh
python build.py --preset minimal -- -DFFMPEG_AVDEVICE=OFF -DFFMPEG_AVFILTER=OFF
```

库开关使用 `FFMPEG_AVUTIL`、`FFMPEG_AVCODEC`、`FFMPEG_AVFORMAT`、`FFMPEG_AVFILTER`、`FFMPEG_AVDEVICE`、`FFMPEG_SWSCALE`、`FFMPEG_SWRESAMPLE`，需保留所选组件的必需依赖。

### 限制部分组件

在 `full` 基础上只指定某一组，其他组继续使用默认选择：

```sh
python build.py -- "-DFFMPEG_ENCODERS=aac;flac;pcm_s16le" -DFFMPEG_HWACCELS=NONE
```

| 参数 | 组件组 |
| --- | --- |
| `FFMPEG_DECODERS` / `FFMPEG_ENCODERS` | 解码器 / 编码器 |
| `FFMPEG_DEMUXERS` / `FFMPEG_MUXERS` | 解封装器 / 封装器 |
| `FFMPEG_PARSERS` / `FFMPEG_BSFS` | 码流解析器 / 位流过滤器 |
| `FFMPEG_FILTERS` / `FFMPEG_PROTOCOLS` | 滤镜 / 输入输出协议 |
| `FFMPEG_INDEVS` / `FFMPEG_OUTDEVS` | 输入 / 输出设备 |
| `FFMPEG_HWACCELS` | 硬件解码加速器 |

每组接受 `AUTO`（跟随预设）、`ALL`、`NONE`，或分号分隔的组件名。含分号的参数需加引号，PowerShell 和 POSIX shell 均适用。

白名单用于选择初始组件，必需依赖会自动加入；`NONE` 清空该组的初始选择。需要明确禁止某个组件及依赖它的组件时，使用 `FFMPEG_DISABLE`：

```sh
python build.py -- "-DFFMPEG_DISABLE=h264_decoder;http_protocol" -DFFMPEG_NETWORK=OFF
```

白名单使用 `h264` 等组内名称，`FFMPEG_DISABLE` 使用 `h264_decoder` 等完整名称。显式请求无法满足依赖的组件会使配置失败。

### 查询与重置

```sh
python tools/configure.py --list decoders
python tools/configure.py --list all
```

每次配置生成 `build/<preset>/generated/components.json`，列出启用组件、未启用原因和实际 FFmpeg 提交。另有 `playback`、`transcode` 示例预设，仅在显式选择时生效。

CMake 会保留上次设置。恢复单组默认值用 `-DFFMPEG_DECODERS=AUTO`；仅改回 `FFMPEG_PROFILE=full` 不会清除已有白名单。以下命令重置当前平台默认预设的 CMake 配置并重新构建，外部依赖缓存仍可复用：

```sh
python build.py -- --fresh
```

## 外部依赖

```sh
# 常用音频、WebP 和文字渲染依赖
python build.py --deps media --action test

# 所有配方；x265 需要显式开启 GPL
python build.py --deps all --action test -- -DFFMPEG_GPL=ON

# 按名称选择，自动补齐依赖
python build.py --deps opus,vorbis,webp
```

PowerShell 对应入口为 `./build.ps1 -Deps media -Action Test`。选择外部库不会改变 FFmpeg 的 `full` 默认配置。

| 配方 | 用途 | `media` |
| --- | --- | --- |
| `zlib` | 压缩、PNG 等内置编码器 | ✓ |
| `opus` | Opus 编解码 | ✓ |
| `ogg` / `vorbis` | Vorbis 编解码 | ✓ |
| `webp` | WebP 静态图像与动画编码 | ✓ |
| `freetype` / `harfbuzz` | 字体、文字排版、`drawtext` | ✓ |
| `aom` | AV1 编解码 | |
| `x265` | HEVC 编码，要求 GPL | |
| `xz` | liblzma 压缩 | |
| `sdl2` | `ffplay` | |

`all` 包含以上 11 个库，版本与提交固定在 [依赖清单](tools/dependencies.json)。全部使用原生 CMake/Ninja 构建为静态库，供 FFmpeg 静态或动态构建使用，并随安装包提供头文件、库、CMake 包和许可证。

默认发现系统已有依赖，不自动下载可选库；缺少 zlib 时会补建，可通过 `FFMPEG_FETCH_ZLIB=OFF` 关闭。AOM 代码生成需要 Perl：Windows 使用 Git for Windows 附带的 Perl，Linux/macOS 使用系统 Perl。

已有依赖安装目录可通过 `FFMPEG_DEPENDENCY_PREFIX` 复用，系统 CMake 包通过 `CMAKE_PREFIX_PATH` 查找。编译器、架构和 C/C++ 运行库需与当前构建兼容。

提供 pkg-config 元数据的外部安装可显式接入：

```sh
python build.py -- "-DFFMPEG_PKG_CONFIG_LIBRARIES=libdav1d;libass;libvpx"
```

此接口还支持 libx264（要求 GPL）、libmp3lame、libsvtav1 及上述音频、字体和 WebP 库；未列入依赖清单的库需自行安装。

## 缓存与构建选项

| 选项 | 默认值 | 说明 |
| --- | --- | --- |
| `BUILD_SHARED_LIBS` | OFF | 构建动态库 |
| `FFMPEG_PROGRAMS` | ON | 构建命令行程序 |
| `FFMPEG_NETWORK` | ON | 网络支持 |
| `FFMPEG_GPL` / `FFMPEG_VERSION3` | OFF | 对应上游许可开关 |
| `FFMPEG_CACHE` | ON | 使用可用的 sccache |
| `FFMPEG_PROBE_CACHE` | ON | 跨构建目录复用平台特性检测 |
| `FFMPEG_PROBE_CACHE_DIR` | `.cache/probes` | 平台检测缓存目录 |
| `FFMPEG_COMPILE_JOBS` / `FFMPEG_LINK_JOBS` | 自动 / 2 | Ninja 编译、链接并发上限 |
| `FFMPEG_ASM` | AUTO | 汇编优化；`ON` 要求所需汇编工具可用，`OFF` 关闭 |
| `FFMPEG_SMALL` | OFF | 体积优化，省略可选描述信息 |
| `FFMPEG_LTO` | OFF | 链接时优化，会增加链接耗时 |

三类缓存独立生效：

- **平台检测**：保存布尔检测结果。编译器、参数、架构、SDK、系统包状态或检测代码改变时失效。自定义 SDK 头文件更新后可更改 `FFMPEG_PROBE_CACHE_SALT`。关闭跨目录缓存时，原目录仍保留 CMake 自带缓存。
- **外部依赖**：按库缓存到 `.cache/dependency-packages`，按所选依赖图合并到 `.cache/dependencies`。兼容的库无需重新配置或编译，新增依赖可复用已有包。
- **编译结果**：sccache 缓存 C/C++ 编译产物，Ninja 跟踪头文件依赖。可使用 `sccache --show-stats` 查看命中情况；Windows 本地安装位于 `.tools/bin/sccache.exe`。

## CMake 集成

安装后，通过 `CMAKE_PREFIX_PATH` 指向 `install/<preset>`：

```cmake
find_package(FFmpeg REQUIRED COMPONENTS avformat avcodec swscale)
target_link_libraries(my_app PRIVATE FFmpeg::avformat FFmpeg::avcodec FFmpeg::swscale)
```

也可通过 `add_subdirectory()` 使用相同目标。示例见 [tests/consumer](tests/consumer)。Windows 动态库运行时需确保安装目录的 `bin` 位于应用的 DLL 搜索路径中。

## 持续集成

[GitHub Actions](https://github.com/SnowLuma/ffmpeg-cmake/actions/workflows/build.yml) 使用五类原生 runner：Windows x64、Linux x64/ARM64、macOS Intel/Apple Silicon，各自构建静态库和动态库。

- 每次运行统一解析 FFmpeg 提交，源码只拉取一次。
- 每个平台准备一次全部外部依赖与特性检测结果，静态、动态任务共用；平台之间独立推进。
- 缓存外部依赖、平台检测、编译产物及工具下载；失败后保留已完成的依赖包。
- 执行媒体往返、外部编解码器、文字渲染、缓存失效、增量构建和安装包消费测试。
- 上传包含程序、库、头文件、CMake 包、许可证及组件清单的安装包，使用快速 gzip 并关闭重复压缩。

手动运行支持 `ffmpeg_branch` 和 `ffmpeg_revision`。CI 开启 GPL 以验证 x265，本地默认关闭。工作流结构参考 [NapNeko/ffmpegAddon](https://github.com/NapNeko/ffmpegAddon/blob/master/.github/workflows/build-ffmpeg-and-addon.yml)。

## 许可证

构建层使用 [LGPL-2.1-or-later](LICENSE)。FFmpeg 与各外部依赖遵循各自许可证，最终产物的许可取决于启用组件和依赖。
