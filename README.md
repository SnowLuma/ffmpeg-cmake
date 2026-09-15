# FFmpeg 原生 CMake 构建

直接从 FFmpeg 源码编译七个库、`ffmpeg`、`ffprobe`，检测到 SDL2 时还会编译 `ffplay`。
**默认 `full`，不按场景裁剪。** 支持组件白名单、依赖自动补齐、Ninja 并行、编译缓存和可选 LTO。

Windows 使用 Visual Studio C++ 工具链或 clang-cl，以及 CMake、Ninja、Python 标准库。
不需要 MSYS2、Cygwin、Bash、GNU Make、Perl、sed 或 awk。
构建不执行 FFmpeg 的 `configure` 或 Makefile。

源码由 `tools/sources.py` 从 [FFmpeg 官方仓库](https://github.com/FFmpeg/FFmpeg) 拉取。
`ffmpeg/` 是忽略的本地目录，不使用子模块、不提交上游源码。默认分支为 `master`。

[![Native FFmpeg](https://github.com/SnowLuma/ffmpeg-cmake/actions/workflows/build.yml/badge.svg)](https://github.com/SnowLuma/ffmpeg-cmake/actions/workflows/build.yml)

## 获取源码

```sh
git clone https://github.com/SnowLuma/ffmpeg-cmake.git
cd ffmpeg-cmake
python tools/sources.py --branch master

# 切换分支；指定分支的兼容性以实际构建结果为准
python tools/sources.py --branch release/8.0

# 可选：固定提交，复现一次构建
python tools/sources.py --branch master --revision 7797fb3ee3620ed4f466d6db3825e12243053055
```

每次显式运行获取脚本都会拉取指定分支。`build.py` 只在源码缺失时自动获取；
传入 `--branch` 则先更新再构建。保留一项本地修改检查，防止切换分支覆盖修改。
实际构建提交记录在 `generated/components.json` 和 `ffmpeg -version` 中。

## Windows 10/11 x64 快速开始

需要安装：

- Visual Studio 2022 / Build Tools，选择“使用 C++ 的桌面开发”，包含 Windows SDK、CMake 和 Ninja。
- Python 3.10+、Git。
- 使用 `windows` 预设时需要 LLVM / clang-cl；`windows-msvc` 使用 Visual Studio 自带的 `cl`。

普通 PowerShell 即可，脚本会自动查找 Visual Studio 并初始化编译环境：

```powershell
# 第一次运行：项目内安装带 SHA256 校验的 NASM、sccache，再完整编译
.\build.ps1 -Bootstrap

# 可选：改用 clang-cl
.\build.ps1 -Preset windows -Bootstrap

# 运行测试 / 安装
.\build.ps1 -Action Test
.\build.ps1 -Action Install
```

默认使用 MSVC，无需安装 LLVM。输出：`build/windows-msvc/bin/ffmpeg.exe`、`ffprobe.exe`、`build/windows-msvc/lib/*.lib`。
安装目录：`install/windows-msvc`。clang-cl 预设使用相应的 `windows` 目录。
动态库也可直接选择 `-Preset windows-shared`（clang-cl）。

`-Bootstrap` 下载固定版本 NASM 3.02 和 sccache 0.18.0 到 `.tools/bin`，不修改系统 PATH，
不需要管理员权限。可自行安装这两个工具，也可省略 `-Bootstrap`：没有缓存工具时仍可构建；
`FFMPEG_ASM=AUTO` 在 NASM 缺失时使用 C 实现，`ON` 则要求安装 NASM。

已打开 Developer PowerShell 时也可直接使用标准 CMake：

```powershell
cmake --preset windows-msvc
cmake --build --preset windows-msvc --parallel 12
ctest --preset windows-msvc
cmake --install build/windows-msvc
```

## 默认功能和可选依赖

`full` 尝试启用所有组件，按编译器、系统 API、已发现的外部依赖和许可选项决定可用性。
每次配置生成 `build/<preset>/generated/components.json`，记录启用组件和每个未启用组件的原因。
明确请求一个无法满足依赖的组件会报错，不会悄悄忽略。

- 自动检测 Windows DXVA2、D3D11VA、D3D12VA、Media Foundation、DirectShow、GDI、VFW、Graphics Capture 和 Schannel。
- 自动检测 zlib、BZip2、LibLZMA、Iconv、SDL2；找不到 zlib 时默认通过原生 CMake 构建固定版本 zlib 1.3.2。
- GPL 和 version3 的默认值遵循上游，均为 OFF。需要对应组件时用 `-DFFMPEG_GPL=ON`、`-DFFMPEG_VERSION3=ON`。
- 外部编码库、GPU SDK 等各自需要独立适配和依赖；没有检测成功的功能不会被冒充为可用。
- 硬件加速编译成功不代表当前机器的 GPU 支持所有编码格式，运行时仍由 FFmpeg 检测。

## Linux / macOS

Ubuntu / Debian：

```sh
sudo apt-get install build-essential cmake ninja-build python3 git nasm zlib1g-dev libbz2-dev liblzma-dev libasound2-dev libsdl2-dev
python3 build.py --preset linux --action test
python3 build.py --preset linux --action install
```

macOS（先安装 Xcode Command Line Tools 和 Homebrew）：

```sh
brew install cmake ninja python nasm sccache sdl2
python3 build.py --preset macos --action test
python3 build.py --preset macos --action install
```

CMake 要求 3.25+，Python 要求 3.10+。`build.py` 默认选择当前系统的预设。
额外 CMake 选项放在 `--` 后，例如：

```sh
python3 build.py --action test --jobs 4 -- -DBUILD_SHARED_LIBS=ON
```

- Linux：pthread、ALSA、V4L2、framebuffer、OSS；以系统头文件和开发库探测结果为准。
- macOS：VideoToolbox、AudioToolbox、AVFoundation、Secure Transport。
- x64 使用 NASM；Linux/macOS ARM64 使用编译器自带汇编器，支持 NEON 和可用的 ARM 扩展。
- 可执行文件在 `build/<preset>/bin`，库在 `build/<preset>/lib`，安装包在 `install/<preset>`。

## 裁剪

默认无需设置任何裁剪选项。以下为按需使用的示例。

### 从空组件集合开始

```powershell
.\build.ps1 -Preset minimal -Jobs 12 `
  '-DFFMPEG_DECODERS=h264;hevc;aac' `
  '-DFFMPEG_DEMUXERS=mov;matroska' `
  '-DFFMPEG_PARSERS=h264;hevc;aac' `
  '-DFFMPEG_PROTOCOLS=file'
```

`minimal` 关闭命令行程序，保留七个库的基础 API。可通过 `-DFFMPEG_AVDEVICE=OFF`、
`-DFFMPEG_AVFILTER=OFF` 等进一步关闭库；库间必需依赖必须保留。

### 只限制一类组件

```powershell
# 其他组仍使用 full 的默认选择
.\build.ps1 '-DFFMPEG_ENCODERS=aac;flac;pcm_s16le' '-DFFMPEG_HWACCELS=NONE'

# 在现有配置中明确禁止特定组件；依赖它的组件也会停用
.\build.ps1 '-DFFMPEG_DISABLE=h264_decoder;http_protocol' -DFFMPEG_NETWORK=OFF
```

组件组参数：

| 参数 | 内容 |
| --- | --- |
| `FFMPEG_DECODERS` / `FFMPEG_ENCODERS` | 解码器 / 编码器 |
| `FFMPEG_DEMUXERS` / `FFMPEG_MUXERS` | 解封装 / 封装 |
| `FFMPEG_PARSERS` / `FFMPEG_BSFS` | 码流解析器 / 位流过滤器 |
| `FFMPEG_FILTERS` / `FFMPEG_PROTOCOLS` | 滤镜 / 输入输出协议 |
| `FFMPEG_INDEVS` / `FFMPEG_OUTDEVS` | 输入 / 输出设备 |
| `FFMPEG_HWACCELS` | 硬件解码加速器 |

值可以是 `AUTO`（使用预设）、`ALL`、`NONE`，或以分号分隔的上游组件名。
白名单是依赖解析的起点；必需的关联组件会自动加入。例如 HEVC 解码会加入 CABAC、Golomb 等模块。
需要严格禁止重新启用时使用 `FFMPEG_DISABLE`。CLI 本身也需要少量基础滤镜。

查询可用名称：

```powershell
python tools/configure.py --list decoders
python tools/configure.py --list protocols
python tools/configure.py --list all
```

组件名以生成列表为准，例如原始 PCM 的封装组件是 `pcm_s16le`，对应 CLI 的 `-f s16le`。
另外提供 `playback` 和 `transcode` 示例预设；这些预设仅在显式选择时生效。
缓存中的自定义选项会保留，恢复组默认值用 `-DFFMPEG_DECODERS=AUTO` 等。

## 编译加速和构建选项

| 选项 | 默认值 | 说明 |
| --- | --- | --- |
| `FFMPEG_CACHE` | ON | 使用 sccache；不覆盖调用方设置的 compiler launcher |
| `FFMPEG_COMPILE_JOBS` | 空 | Ninja 默认并行数；也可用 `build.ps1 -Jobs 12` |
| `FFMPEG_LINK_JOBS` | 2 | 限制同时链接数量 |
| `FFMPEG_ASM` | AUTO | 启用本架构汇编实现和运行时 CPU 分派 |
| `FFMPEG_LTO` | OFF | 跨文件优化；会增加链接时间，不是缩短全量构建时间的开关 |
| `FFMPEG_SMALL` | OFF | 省略非必要描述信息，使用体积优化 |
| `BUILD_SHARED_LIBS` | OFF | 构建动态库 |
| `FFMPEG_PROGRAMS` | ON | 构建命令行程序 |
| `FFMPEG_NETWORK` | ON | 网络支持 |
| `FFMPEG_FETCH_ZLIB` | ON | 缺少系统 zlib 时下载并构建固定版本 |

元数据文件内容不变时不重写，防止配置过程触发无意义的全量重编译。
Ninja 跟踪 C/C++、预处理汇编和 NASM 的头文件依赖；Release 不生成调试信息，Debug/RelWithDebInfo 使用嵌入式调试信息，适配编译缓存。
MSVC 使用原生 `/sourceDependencies` JSON 提供头文件依赖，避免中文版工具链和缓存输出编码造成漏编译。

```powershell
.tools/bin/sccache.exe --show-stats
```

## 在其他 CMake 工程中使用

先安装，再通过 `CMAKE_PREFIX_PATH` 指向安装目录：

```cmake
find_package(FFmpeg REQUIRED COMPONENTS avformat avcodec swscale)
target_link_libraries(my_app PRIVATE FFmpeg::avformat FFmpeg::avcodec FFmpeg::swscale)
```

或将本项目通过 `add_subdirectory()` 引入，使用同样的 `FFmpeg::` 目标。
可运行 `tests/consumer` 验证安装包；静态库的系统库和压缩库依赖由导出的 CMake 目标传递。

## GitHub Actions

[构建工作流](.github/workflows/build.yml) 包含 Windows x64、Linux x64/ARM64、macOS Intel/Apple Silicon，
每个平台都构建静态库和动态库。默认 `full`，不按场景裁剪。
手动运行可选择 `ffmpeg_branch` 和 `ffmpeg_revision`；各矩阵任务使用同一个解析后的提交。

- sccache 使用 GitHub Actions cache 保存编译结果；Windows 下载包使用 `actions/cache`。
- 执行真实媒体往返、头文件增量编译检查，以及安装后独立 C 项目的链接与运行测试。
- 安装产物打包为 `.tar.gz` 上传，包含程序、头文件、库、CMake 包、许可证和组件报告。
- 缓存只加速构建，每次都重新配置并运行测试。失败时上传配置日志和组件报告。

工作流的多平台构建与产物上传安排参考了
[NapNeko/ffmpegAddon](https://github.com/NapNeko/ffmpegAddon/blob/master/.github/workflows/build-ffmpeg-and-addon.yml)。
本项目使用 Python + CMake + Ninja，不需要该参考工程的 MSYS2 或 autotools 环境。

## 实现结构

- `CMakeLists.txt`：原生库、程序、生成规则、安装包和测试目标。
- `build.py`：统一的跨平台构建入口；`build.ps1` 仅转发参数。
- `tools/sources.py`：浅克隆、分支更新和可选的固定提交检出。
- `cmake/platform/`：Windows、POSIX、Apple 框架和原生汇编支持，探测不运行目标程序。
- `cmake/Dependencies.cmake`：原生依赖发现和固定版本依赖构建。
- `tools/configure.py`：用 Python 标准库读取上游声明式依赖/文件列表，计算组件闭包，生成配置头、注册表和 CMake 源文件列表。不会执行这些上游脚本。
- `tools/capture.py`：捕获预处理器和 ARM64 代码生成工具的输出，无 shell 管道。
- `tests/`：依赖解析回归、真实媒体往返测试、安装包消费示例。

本机验证范围和可复现命令见 [VALIDATION.md](VALIDATION.md)。

未识别的已选源文件、表达式或缺失规则会使配置失败，便于在升级上游时补齐适配。
上游保留其许可证；本构建层使用 LGPL-2.1-or-later，见 `LICENSE`。
