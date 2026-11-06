# VanishCam for macOS (Goku Instant Transmission / Naruto / Particles / Dissolve)

> Real-time webcam disappearance & Dragon Ball **Goku Instant Transmission (瞬间移动)** effects for macOS and Windows — powered by MediaPipe & OpenCV, with global hotkey control (`Command + Shift + T`) and zero video overlay clutter.

基于 [Nicovic17/vanish_webcam](https://github.com/Nicovic17/vanish_webcam) 深度完善与移植的 **macOS 增强版**。补全了原仓库未公开的 **Goku 瞬间移动模式（龙珠双指抵额头瞬移）** 与 **Particles 粒子消散模式**，修复了 Apple Silicon (M1/M2/M3/M4) 上的 MediaPipe Metal 闪退问题，并新增了系统级全局快捷键与独立桌面悬浮提醒。

## ✨ 核心特性 (Key Features)

1. **四种实时特效模式 (4 Vanish Modes)**：

   * **4 - Goku Teleport (悟空瞬间移动)**：食指与中指并拢抵住额头保持 **1 秒**，伴随漫画纵向速度线与经典瞬移音效 (`assets/teleport.MP3`) 瞬间消失；放下手再次抵住额头 1 秒即可反向瞬移归来。

   * **2 - Naruto Vanish (火影替身术)**：双手合十结印，爆开烟雾并落下替身木桩 (`assets/vanish.MP3`)。

   * **3 - Particles (粒子消散)**：比出剪刀手 (V 手势)，身体轮廓碎裂为彩色微粒随风飘散。

   * **1 - Normal Vanish (经典渐变隐身)**：比出剪刀手 (V 手势)，身体在微光中平滑消融。

2. **全局快捷键开关手势识别 (`Command + Shift + T`)**：

   * 背景采集完成后默认**关闭手势识别**，保证平时视频会议画面 100% 满帧流畅、零额外算力消耗。

   * 即使正在全屏使用腾讯会议、Zoom、飞书或浏览器，按下 **`Command + Shift + T`** 即可随时开启/关闭手势识别。

3. **OBS 画面 100% 纯净（独立桌面 HUD + 系统通知提醒）**：

   * 状态提示通过 **macOS 独立置顶悬浮窗 (`NSPanel`) + 系统通知中心** 显示并在 3 秒后自动消失，**绝不绘制在摄像头画面内**，确保 OBS 窗口采集转发给会议对方时看不到任何文字提示。

4. **双击即用 (`VanishCam.app`) & 独立视频转场工具 (`goku_video_transition.py`)**：

   * 内置原生 `VanishCam.app`、一键启动脚本与 DMG 打包工具，同时附带独立的视频剪辑转场生成脚本。

## 🚀 快速开始 (Quick Start on macOS)

### 方式一：双击应用程序直接运行（免命令行）

1. 双击运行目录中的 **`VanishCam.app`**（或直接双击 **`启动Goku瞬移模式.command`**）。

2. 若首次运行提示“无法验证开发者”，**右键点击 `VanishCam.app` -> 选择“打开”** 即可。

3. 如需打包为拖拽式 `.dmg` 安装镜像，双击运行 **`一键生成DMG安装包.command`** 即可在当前目录生成 `VanishCam_macOS.dmg`。

### 方式二：终端命令行运行

```
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

## 🎮 使用流程与快捷键 (Workflow & Controls)

```
启动程序 ──► 10秒倒计时采集干净背景 (人暂时离开画面)
         ──► 默认满帧待机 (不识别手势，画面流畅不掉帧)
         ──► 按下 Command + Shift + T (开启手势识别，桌面顶部弹出3秒提醒)
         ──► 双指并拢抵住额头 1 秒 ──► 瞬间移动消失！
         ──► 再次双指抵住额头 1 秒 ──► 反向瞬移现身！
         ──► 再次按下 Command + Shift + T (关闭手势识别，恢复满帧待机)

```

| 快捷键 | 功能说明 | 
| ----- | ----- | 
| **`Command + Shift + T`** *(全局)* 或 **`T`** *(窗口内)* | **开启 / 关闭手势识别**（支持在任何会议软件全屏时后台触发） |
| **`Command + Shift + C`** *(全局)* 或 **`C`** *(菜单/窗口内)* | **手动切换摄像头设备**（可在启动菜单选定，也可在运行中随时热切换并重新采集背景） |
| **`SPACE` / `W`** | 重新触发 10 秒背景采集倒计时 | 
| **`F`** | 切换全屏预览 | 
| **`V` / `R`** | 手动触发消失 / 现身（注：Goku 模式下禁用，仅限手势触发） | 
| **`Q` / `ESC`** | 退出程序并释放摄像头 | 

## 🎥 接入线上会议软件 / 网页 (OBS Virtual Camera)

1. 打开 **OBS Studio**，在底部“来源 (Sources)”点击 **`+`** -> 选择 **“macOS 屏幕采集 (macOS Screen Capture)”** 或 **“窗口采集 (Window Capture)”**。

2. 将采集方法设为 **窗口采集**，选择窗口 **`[python3] Webcam - Preview`**（取消勾选“显示光标”）。

3. 点击 OBS 右下角 **“启动虚拟摄像机 (Start Virtual Camera)”**。

4. 在腾讯会议、Zoom、Teams、Google Meet 或浏览器网页中选择 **`OBS Virtual Camera`** 作为摄像头设备。

## 🎬 独立视频转场生成器 (`goku_video_transition.py`)

如果你想在视频剪辑中使用悟空瞬间移动的纵向速度线与闪烁转场：

```
# 在两段视频素材之间自动合成悟空瞬间移动转场
python3 goku_video_transition.py --clip-a scene1.mp4 --clip-b scene2.mp4 --output final_edit.mp4

```

## 📜 Credits & License

* Original concept & base implementation by [Nicovic17/vanish_webcam](https://github.com/Nicovic17/vanish_webcam).

* Goku Instant Transmission (`goku_effect.py`), Particles mode (`particles_effect.py`), macOS global hotkey & native HUD overlay, and macOS bundle packaging added in this repository.