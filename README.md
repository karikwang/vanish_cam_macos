# VanishCam for macOS (Goku 瞬间移动 / 火影替身术 / 粒子消散 / 渐变隐身)

<p align="left">
  <strong>🌐 语言 / Language:</strong>
  <b>简体中文</b> | <a href="./README_EN.md">English</a>
</p>


> 基于 MediaPipe 与 OpenCV 的 macOS / Windows 实时摄像头隐身与《龙珠》孙悟空瞬间移动（Instant Transmission）特效工具——支持系统级全局快捷键（`Command + Shift + T`）与独立桌面悬浮提醒，摄像头画面 100% 纯净无文字遮挡。

本项目是基于 [Nicovic17/vanish_webcam](https://github.com/Nicovic17/vanish_webcam) 深度完善与移植的 macOS 增强版。补全了原仓库未公开的 Goku 瞬间移动模式（双指抵额头瞬移） 与 Particles 粒子消散模式，修复了 Apple Silicon (M1/M2/M3/M4) 上的 MediaPipe Metal 闪退问题，并新增了摄像头手动/热切换、全局快捷键及原生 `.app` / `.dmg` 安装包。

## 📥 如何下载（零代码基础小白指南）

如果你不熟悉代码或 Git，只需任选以下一种方式即可直接在 Mac 上双击使用：

### 方式 A：直接下载 `.dmg` 安装包（最推荐）

1. 点击进入本仓库的 **[`release/VanishCam_macOS.dmg`](./release/VanishCam_macOS.dmg)**（或点击页面右侧 Releases 下载 `VanishCam_macOS.dmg`）。
2. 双击挂载打开 `VanishCam_macOS.dmg`，将里面的 `VanishCam.app` 拖到桌面或“应用程序 (Applications)”文件夹中，双击即可运行！

### 方式 B：下载整个项目 ZIP 压缩包

1. 在当前 GitHub 页面右上角，点击绿色的 `< > Code` 按钮，然后点击弹出菜单底部的 `Download ZIP`。
2. 解压下载好的 `.zip` 文件，打开文件夹直接双击里面的 `VanishCam.app` 即可运行！
3. *(注：首次启动时会自动在后台配置运行环境，耗时约 1 分钟；若 macOS 弹出“无法验证开发者”的安全提示，只需右键点击 `VanishCam.app` -> 选择“打开”即可)*。

*(熟悉 Git 的开发者也可以直接在终端执行：`git clone <本仓库地址>` 下载)*

## ✨ 核心特性

1. **四种实时特效模式**：

   - 1 - Normal Vanish (经典渐变隐身)：比出剪刀手 (V 手势)，身体在微光中平滑消融。

   * 2 - Naruto Vanish (火影替身术)：双手合十结印，爆开烟雾并落下替身木桩 (`assets/vanish.MP3`)。
   * 3 - Particles (粒子消散)：比出剪刀手 (V 手势)，身体轮廓碎裂为彩色微粒随风飘散。
   * 4 - Goku Teleport (悟空瞬间移动)：食指与中指并拢抵住额头保持 1 秒，伴随漫画纵向速度线与经典瞬移音效 (`assets/teleport.MP3`) 瞬间消失；放下手再次抵住额头 1 秒即可反向瞬移归来。

2. **全局快捷键开关手势识别 (`Command + Shift + T`)**：

   * 背景采集完成后默认关闭手势识别，保证平时视频会议画面 100% 满帧流畅、零额外算力消耗。
   * 即使正在全屏使用腾讯会议、Zoom、飞书或浏览器，按下 `Command + Shift + T` 即可随时开启/关闭手势识别。

3. **支持手动选择与随时热切换摄像头 (`Command + Shift + C` / `C`)**：

   * 启动菜单底部自带摄像头选择栏，可点击或按 `C` 键提前选定摄像头。
   * 进入视频画面后若发现选错了摄像头，无需退出重启，随时按 `C` 键或全局快捷键 `Command + Shift + C` 即可切换到下一个摄像头并重新采集背景。

4. **OBS 画面 100% 纯净（独立桌面 HUD + 系统通知提醒）**：

   * 状态提示通过 macOS 独立置顶悬浮窗 (`NSPanel`) + 系统通知中心 显示并在 3 秒后自动消失，绝不绘制在摄像头画面内，确保 OBS 窗口采集转发给会议对方时看不到任何文字提示。

5. **双击即用 (`VanishCam.app` & `VanishCam_macOS.dmg`)**：

   * 内置原生 `VanishCam.app` 与打包好的 `release/VanishCam_macOS.dmg`，无需每次打开终端手敲命令。

## 🚀 快速开始 (macOS)

### 方式一：双击应用程序直接运行（免命令行）

1. 双击运行目录中的 `VanishCam.app`（或挂载 `release/VanishCam_macOS.dmg` 后将 `VanishCam.app` 拖入应用程序运行）。
2. 若首次运行提示“无法验证开发者”，右键点击 `VanishCam.app` -> 选择“打开” 即可。

### 方式二：终端命令行运行

```zsh
# 1. 创建并激活 Python 虚拟环境 (推荐 Python 3.10 或 3.11)
python3 -m venv .venv
source .venv/bin/activate

# 2. 安装依赖 (已针对 macOS Apple Silicon 自动锁定稳定版 MediaPipe)
pip install -r requirements.txt

# 3. 启动 Goku 瞬间移动模式
python3 vanish_cam.py --mode goku --no-virtual-camera

# 或者打开 1~4 模式图形选择菜单
./vanish --no-virtual-camera
```

## 🎮 使用流程与快捷键

```text
启动程序 ──► 10秒倒计时采集干净背景 (人暂时离开画面)
         ──► 默认满帧待机 (不识别手势，画面流畅不掉帧)
         ──► 按下 Command + Shift + T (开启手势识别，桌面顶部弹出3秒提醒)
         ──► 双指并拢抵住额头 1 秒 ──► 瞬间移动消失！
         ──► 再次双指抵住额头 1 秒 ──► 反向瞬移现身！
         ──► 再次按下 Command + Shift + T (关闭手势识别，恢复满帧待机)
```

| 快捷键                                                   | 功能说明                                                     |
| :------------------------------------------------------- | :----------------------------------------------------------- |
| `Command + Shift + T` *(全局)* 或 **`T`** *(窗口内)*     | 开启 / 关闭手势识别（支持在任何会议软件全屏时后台触发）      |
| `Command + Shift + C` (全局)* 或 **`C`** *(菜单/窗口内)* | 手动切换摄像头设备（可在启动菜单选定，也可在运行中随时热切换并重新采集背景） |
| `SPACE` / `W`                                            | 重新触发 10 秒背景采集倒计时                                 |
| `F`                                                      | 切换全屏预览                                                 |
| `V` / `R`                                                | 手动触发消失 / 现身（注：Goku 模式下禁用，仅限手势触发）     |
| `Q` / `ESC`                                              | 退出程序并释放摄像头                                         |

## 🎥 接入线上会议软件 / 网页 (OBS Virtual Camera)

1. 打开 [OBS Studio](https://obsproject.com/)，在底部“来源 (Sources)”点击 `+` -> 选择 “macOS 屏幕采集 (macOS Screen Capture)” 或 “窗口采集 (Window Capture)”。
2. 将采集方法设为 窗口采集，选择窗口 `[python3] Webcam - Preview`（取消勾选“显示光标”）。
3. 点击 OBS 右下角 “启动虚拟摄像机 (Start Virtual Camera)”。
4. 在腾讯会议、Zoom、Teams、Google Meet 或浏览器网页中选择 `OBS Virtual Camera` 作为摄像头设备。

## 🙏 致谢与许可声明 (Acknowledgements & License)

* 致谢原作者 (Upstream Attribution)：本项目的最初创意与基础实现源自 Nico Auriemma 的开源项目 [Nicovic17/vanish_webcam](https://github.com/Nicovic17/vanish_webcam)。感谢原作者出色的创意设计！
* 本项目新增与改进内容 (Contributions in this Fork)：
  * 独立编写并开源了 Goku 瞬间移动模式 (`goku_effect.py`) 与 Particles 粒子消散模式 (`particles_effect.py`)。
  * 新增了 macOS 系统级全局快捷键 (`Command + Shift + T` / `Command + Shift + C`)、摄像头选择与实时热切换、以及独立桌面悬浮窗 (`NSPanel`) 与系统通知提醒。
  * 修复了 Apple Silicon Mac 上的 MediaPipe Metal 崩溃问题，并提供了原生 `VanishCam.app` 与 `VanishCam_macOS.dmg` 安装包。
* 开源协议与免责声明 (License & Disclaimer)：
  * 本仓库中新增的移植与扩展代码采用 [MIT License](./LICENSE) 开源协议，仅供个人学习、技术交流与非商业用途使用。
  * 原项目基础代码归原作者 [Nicovic17](https://github.com/Nicovic17/vanish_webcam) 所有；音效与动漫招式灵感（《七龙珠》、《火影忍者》）的相关知识产权归各自版权方所有。
