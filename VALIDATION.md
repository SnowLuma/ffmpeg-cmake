# 验证记录

日期：2026-09-15。下表为本机 Windows x64 实测记录。

跨平台构建和安装测试由 [GitHub Actions](https://github.com/SnowLuma/ffmpeg-cmake/actions/workflows/build.yml) 执行；
每个任务的实际状态、FFmpeg 提交和安装产物均在对应运行中保存。
FFmpeg：`7797fb3ee3620ed4f466d6db3825e12243053055`，源码工作区未修改。

## CI 矩阵

运行：[Native FFmpeg #34956378239](https://github.com/SnowLuma/ffmpeg-cmake/actions/runs/34956378239)。
构建代码：`2d3b58e`，默认 `full`，汇编开启，GPL / version3 使用上游默认值。

| 原生 runner | 静态库 | 动态库 |
| --- | --- | --- |
| Windows x64 / MSVC | 通过 | 通过 |
| Linux x64 / GCC | 通过 | 通过 |
| Linux ARM64 / GCC | 通过 | 通过 |
| macOS Intel / AppleClang | 通过 | 通过 |
| macOS Apple Silicon / AppleClang | 通过 | 通过 |

每组执行 CTest 5 项测试、安装后的独立 C 项目测试和头文件增量编译检查。
安装包按平台与静态/动态类型上传到上述运行的 Artifacts。Linux x64 静态任务观测到
762 次 sccache 命中；这是缓存生效的记录，不是固定提速比例的基准测试。

## 本机工具链

| 工具 | 版本 |
| --- | --- |
| Visual Studio MSVC | 19.44.35228 |
| LLVM / clang-cl | 22.1.0 |
| Windows SDK | 10.0.26100.0 |
| CMake | 3.31.6-msvc6 |
| Ninja | 1.12.1 |
| Python | 配置阶段 3.10.5，辅助验证 3.13.12 |
| NASM | 3.02 |
| sccache | 0.18.0 |
| 自动构建的 zlib | 1.3.2，锁定源码提交 |

## 本机补充验证

| 配置 / 检查 | 结果 |
| --- | --- |
| `windows-msvc`，默认完整静态构建 | 七个库、ffmpeg、ffprobe 成功；CTest 5/5 |
| `windows-shared`，clang-cl 完整 DLL 构建 | 七个 DLL、ffmpeg、ffprobe 成功；CTest 5/5 |
| MSVC 完整 DLL 构建 | 公共 API 导出、CTest 5/5、安装后的 C 项目链接与运行通过 |


| 独立 CMake / C 消费项目 | 安装包静态链接、DLL 链接与运行通过；也验证了含空格的构建路径 |
| 源码获取工具 | 从本地 Git 仓库浅克隆指定分支、切换分支、固定提交和本地修改保护通过 |
| 增量构建 | 未修改时 Ninja 无任务；仅改变 adler32.h 时间戳时安排 adler32.c 重编译，随后恢复原时间戳 |
| 编译缓存 | 实际使用 sccache，观测到缓存命中；MSVC 缓存命中后仍正确记录头文件依赖 |

CTest 包含：12 项元数据/依赖回归测试、源码获取测试、两个 CLI 启动测试、真实媒体测试。
媒体测试覆盖 FLAC 音频无损往返、FFV1/Matroska 视频无损往返、PNG 图像无损往返、
ffprobe JSON 元数据，以及本地 HTTP 服务器上的媒体探测。

初始 `5b9a3ad` 版本还验证过 clang-cl 静态构建、无汇编的最小裁剪构建及 MSBuild DLL 构建。
并使用独立安装的 FFmpeg 的 libx264/libx265 生成 H.264 和 HEVC 码流，
新构建的普通 CPU 分派模式及 `-cpuflags 0` 模式均逐字节匹配参考解码器的 8 帧输出。

默认完整配置实际启用：500 个解码器、184 个编码器、67 个解析器、51 个位流过滤器、
28 个硬件解码加速器、362 个解封装器、187 个封装器、36 个协议、4 个输入设备、447 个可选滤镜。
滤镜迭代器还包含上游固定的 4 个 buffer 端点，因此消费程序报告 filters=451。
具体名称、未启用原因和程序列表以各构建目录的 `generated/components.json` 为准。

## 复现

```powershell
.\build.ps1 -Preset windows-msvc -Bootstrap -Action Test
.\build.ps1 -Preset windows -Action Test
.\build.ps1 -Preset windows-shared -Action Test

.\build.ps1 -Preset minimal -DFFMPEG_ASM=OFF -DFFMPEG_NETWORK=OFF
python tests/incremental.py --build build/windows-msvc

# 额外对照测试；reference 需要提供 libx264/libx265
python tests/reference_decode.py `
  --ffmpeg build/windows-msvc/bin/ffmpeg.exe `
  --reference C:/path/to/reference/ffmpeg.exe
```

安装消费示例：

```powershell
.\build.ps1 -Action Install
cmake -S tests/consumer -B build/consumer-check -G 'Visual Studio 17 2022' -A x64 `
  -DCMAKE_PREFIX_PATH="$PWD/install/windows-msvc"
cmake --build build/consumer-check --config Release
ctest --test-dir build/consumer-check -C Release --output-on-failure
```

测试动态库消费程序时，将对应安装目录的 `bin` 加入该进程的 PATH。

## 验证边界

- 本机没有 SDL2 开发包，因此没有生成或验证 ffplay。
- 硬件 API 的检测、编译和注册已验证；未执行屏幕采集，也未针对每种 GPU 做硬件编解码测试。
- Linux、macOS、ARM64 使用 CI 原生 runner 验证；本机没有这些运行环境。
- LTO 和全部第三方编码库/GPU SDK 的组合尚未覆盖。
- 缓存命中数量来自开发期间多轮构建，不能作为固定的编译提速比例。
