# Architecture Document / 架构文档

**Project / 项目**: reBot Arm + reSpeaker Flex  
**Version / 版本**: v1.0.0  
**Date / 日期**: 2025-05-20

---

## 1. System Overview / 系统概述

**English**

The reBot Arm + reSpeaker Flex project is a Python-based robotic control system that integrates a 6-DOF robotic arm with a 4-microphone array. It operates in two primary modes: **DOA (Direction of Arrival) sound source tracking** and **voice command control**. The system combines real-time audio processing, large language model inference, and precise servo motor control into a unified interactive robot platform.

Core capabilities:
- Real-time DOA estimation via reSpeaker Flex XVF3800 4-mic array
- Voice recognition via Groq STT (Whisper) and command parsing via Groq LLM (Llama)
- Text-to-speech feedback via edge-tts
- 6-DOF robotic arm control with joint limit protection and motion interpolation
- Safety mechanisms: cooldown, anti-jitter, URDF-compliant limits

**中文**

reBot Arm + reSpeaker Flex 项目是一个基于 Python 的机器人控制系统，集成六自由度机械臂与四麦克风阵列。系统在两种主要模式下运行：**DOA 声源追踪模式**和**语音指令控制模式**。该系统将实时音频处理、大语言模型推理和精确的伺服电机控制整合为统一的交互式机器人平台。

核心能力：
- 通过 reSpeaker Flex XVF3800 四麦克风阵列进行实时 DOA 估计
- 通过 Groq STT (Whisper) 进行语音识别，通过 Groq LLM (Llama) 进行指令解析
- 通过 edge-tts 提供文本转语音反馈
- 六自由度机械臂控制，具备关节限位保护和运动插值
- 安全机制：冷却、防抖、URDF 合规限位

```
+------------------------------------------------------------------+
|                         System Architecture                       |
+------------------------------------------------------------------+
|                                                                   |
|   +-------------+      +-------------+      +-------------+      |
|   |  reSpeaker  |      |    Groq     |      |   edge-tts  |      |
|   |  Flex XVF   |<---->|    Cloud    |<---->|   Engine    |      |
|   |  4-Mic Array|      |  STT + LLM  |      |             |      |
|   +------+------+      +------+------+      +------+------+      |
|          |                    |                    |              |
|          v                    v                    v              |
|   +-------------+      +-------------+      +-------------+      |
|   | DOA Engine  |      |  Voice Asst |      |  TTS Output |      |
|   |  (ODAS)     |      | (STT+LLM)   |      |  (Audio)    |      |
|   +------+------+      +------+------+      +------+------+      |
|          |                    |                    |              |
|          v                    v                    |              |
|   +-------------+      +-------------+           |              |
|   |  SysMain    |<---->|   ArmCtrl   |<----------+              |
|   |  (State)    |      | (6-DOF Arm) |                          |
|   |  (Modes)    |      | (B601-DM)   |                          |
|   +-------------+      +-------------+                          |
|                                                                   |
+------------------------------------------------------------------+
```

---

## 2. Module Design / 模块设计

### 2.1 ReSpeaker Module / 麦克风阵列模块

**English**

The ReSpeaker module handles all audio input processing using the reSpeaker Flex XVF3800 4-microphone array.

| Component | Description |
|-----------|-------------|
| `DOA Engine` | Extracts Direction of Arrival from audio streams using ODAS or XVF3800 firmware |
| `Audio Capture` | Raw audio stream acquisition from 4-channel microphone array |
| `Angle Output` | Provides DOA angle (0-360 degrees) to SysMain for arm tracking |

- **Input**: Ambient audio from physical environment
- **Output**: DOA angle (degrees), audio stream for STT
- **Dependencies**: `pyaudio`, `odas` (optional), XVF3800 firmware

**中文**

ReSpeaker 模块使用 reSpeaker Flex XVF3800 四麦克风阵列处理所有音频输入。

| 组件 | 说明 |
|------|------|
| `DOA 引擎` | 使用 ODAS 或 XVF3800 固件从音频流中提取到达方向 |
| `音频捕获` | 从四通道麦克风阵列获取原始音频流 |
| `角度输出` | 向 SysMain 提供 DOA 角度（0-360度）用于机械臂追踪 |

- **输入**: 物理环境的环境音频
- **输出**: DOA 角度（度），用于 STT 的音频流
- **依赖**: `pyaudio`, `odas`（可选）, XVF3800 固件

### 2.2 ArmCtrl Module / 机械臂控制模块

**English**

The ArmCtrl module manages all robotic arm motion, including joint control, limit enforcement, and animation.

| Component | Description |
|-----------|-------------|
| `Joint Controller` | Direct servo control for 6 DOF joints (base, shoulder, elbow, wrist1, wrist2, gripper) |
| `Limit Enforcer` | URDF-compliant joint angle limits to prevent mechanical damage |
| `Motion Interpolator` | Smooth motion transitions between positions |
| `Animator` | Built-in animations: breathing standby, tracking motion, wave, dance |
| `Safety Monitor` | Cooldown enforcement, anti-jitter filtering |

- **Input**: Target joint angles / animation commands from SysMain
- **Output**: Servo signals to B601-DM arm
- **Dependencies**: Servo driver library, URDF config

**中文**

ArmCtrl 模块管理所有机械臂运动，包括关节控制、限位执行和动画。

| 组件 | 说明 |
|------|------|
| `关节控制器` | 六自由度关节（底座、肩、肘、腕1、腕2、夹爪）的直接伺服控制 |
| `限位执行器` | 符合 URDF 的关节角度限制，防止机械损坏 |
| `运动插值器` | 位置之间的平滑运动过渡 |
| `动画器` | 内置动画：呼吸待机、追踪运动、挥手、跳舞 |
| `安全监控器` | 冷却强制执行、防抖过滤 |

- **输入**: 来自 SysMain 的目标关节角度 / 动画指令
- **输出**: 发送至 B601-DM 机械臂的伺服信号
- **依赖**: 伺服驱动库，URDF 配置

### 2.3 VoiceAsst Module / 语音助手模块

**English**

The VoiceAsst module provides natural language interaction capabilities.

| Component | Description |
|-----------|-------------|
| `STT Client` | Speech-to-text via Groq API (Whisper model) |
| `LLM Client` | Natural language understanding via Groq API (Llama model) |
| `Command Parser` | Extracts actionable intents from LLM responses |
| `TTS Client` | Text-to-speech via edge-tts for audio feedback |
| `Prompt Manager` | System prompts and context management for LLM |

- **Input**: Audio stream (for STT), text commands
- **Output**: Parsed intents, synthesized speech
- **Dependencies**: `groq`, `edge-tts`, API keys

**中文**

VoiceAsst 模块提供自然语言交互能力。

| 组件 | 说明 |
|------|------|
| `STT 客户端` | 通过 Groq API (Whisper 模型) 进行语音转文本 |
| `LLM 客户端` | 通过 Groq API (Llama 模型) 进行自然语言理解 |
| `指令解析器` | 从 LLM 响应中提取可执行意图 |
| `TTS 客户端` | 通过 edge-tts 进行文本转语音，提供音频反馈 |
| `提示管理器` | LLM 的系统提示和上下文管理 |

- **输入**: 音频流（用于 STT），文本指令
- **输出**: 解析后的意图，合成语音
- **依赖**: `groq`, `edge-tts`, API 密钥

### 2.4 SysMain Module / 系统主控模块

**English**

SysMain is the central coordinator that manages system lifecycle, mode switching, and state transitions.

| Component | Description |
|-----------|-------------|
| `State Machine` | Core state management (see Section 4) |
| `Mode Manager` | Switches between DOA tracking and voice command modes |
| `Signal Handler` | SIGINT/SIGTERM handling for graceful shutdown |
| `Config Loader` | Loads configuration from environment variables and config files |
| `Logger` | Structured logging for all system events |

- **Input**: User commands, DOA angles, system signals
- **Output**: Arm control commands, mode status
- **Dependencies**: Python `logging`, `signal`, `os`

**中文**

SysMain 是中央协调器，管理系统生命周期、模式切换和状态转换。

| 组件 | 说明 |
|------|------|
| `状态机` | 核心状态管理（见第4节） |
| `模式管理器` | 在 DOA 追踪和语音指令模式之间切换 |
| `信号处理器` | 处理 SIGINT/SIGTERM 以实现优雅关机 |
| `配置加载器` | 从环境变量和配置文件加载配置 |
| `日志器` | 所有系统事件的结构化日志 |

- **输入**: 用户指令，DOA 角度，系统信号
- **输出**: 机械臂控制指令，模式状态
- **依赖**: Python `logging`, `signal`, `os`

---

## 3. Data Flow / 数据流

**English**

```
                    +------------------+
   Environment      |  reSpeaker Flex  |
   Audio ---------> |  (4-Mic Array)   |
                    +--------+---------+
                             |
                    +--------v---------+     +------------------+
                    |    DOA Engine    |     |   Audio Buffer   |
                    |  (Angle Output)  |     |  (for STT/LLM)   |
                    +--------+---------+     +--------+---------+
                             |                      |
                    +--------v---------+     +-----v------------+
                    |     SysMain      |<----|   VoiceAsst      |
                    |  (State Machine) |     |  (STT -> LLM)    |
                    +--------+---------+     +------------------+
                             |
                    +--------v---------+
                    |     ArmCtrl      |
                    |  (6-DOF Control) |
                    +--------+---------+
                             |
                    +--------v---------+
                    |  reBot Arm B601  |
                    |   (Physical)     |
                    +------------------+
```

**中文**

```
                    +------------------+
   环境音频          |  reSpeaker Flex  |
   ----------------> |  (四麦克风阵列)   |
                    +--------+---------+
                             |
                    +--------v---------+     +------------------+
                    |    DOA 引擎      |     |   音频缓冲区      |
                    |  (角度输出)      |     |  (用于 STT/LLM)  |
                    +--------+---------+     +--------+---------+
                             |                      |
                    +--------v---------+     +-----v------------+
                    |     SysMain      |<----|   VoiceAsst      |
                    |   (状态机)       |     |  (STT -> LLM)    |
                    +--------+---------+     +------------------+
                             |
                    +--------v---------+
                    |     ArmCtrl      |
                    |  (六自由度控制)   |
                    +--------+---------+
                             |
                    +--------v---------+
                    |  reBot Arm B601  |
                    |    (物理设备)    |
                    +------------------+
```

### Data Types / 数据类型

| Data / 数据 | Type / 类型 | Description / 说明 |
|-------------|-------------|-------------------|
| `DOA Angle` | `float` (0-360) | Sound source direction in degrees / 声源方向角度 |
| `Joint Angles` | `list[float]` (6) | Target angles for 6 joints / 6 个关节的目标角度 |
| `Voice Command` | `str` | Parsed natural language command / 解析后的自然语言指令 |
| `Intent` | `dict` | Structured command with action and params / 带动作和参数的结构化指令 |
| `TTS Text` | `str` | Response text for voice synthesis / 用于语音合成的响应文本 |

---

## 4. State Machine / 状态机

**English**

The system operates as a finite state machine with the following states and transitions:

```
                    +-----------+
           +------->|   IDLE    |<--------+
           |        | (Breath)  |         |
           |        +----+------+         |
           |             |                |
           |  Voice cmd  |  DOA detected  |
           |             v                |
           |        +----+------+         |
           |        | TRACKING  |         |
           |        | (Follow)  |         |
           |        +----+------+         |
           |             |                |
           |   Voice cmd |  Wave cmd      |
           |             v                |
           |        +----+------+         |
           |   +--->|  WAVING   |         |
           |   |    | (Wave)    |         |
           |   |    +----+------+         |
           |   |         |                |
           |   | Dance cmd|  Timeout       |
           |   |         v                |
           |   |    +----+------+         |
           |   +---+|  DANCING  |         |
           |        | (Dance)   |---------+
           |        +----+------+
           |             |
           |  Shutdown   |
           v             v
      +-----------------------+
      |       SHUTDOWN        |
      |  (Cleanup & Exit)     |
      +-----------------------+
```

**States:**

| State | Description | Arm Behavior |
|-------|-------------|--------------|
| `IDLE` | System standby | Breathing animation (slow periodic motion) |
| `TRACKING` | DOA tracking mode | Arm follows sound source direction |
| `WAVING` | Wave animation | Executes pre-programmed wave gesture |
| `DANCING` | Dance animation | Executes pre-programmed dance sequence |
| `VOICE` | Voice command processing | Executes LLM-parsed command |
| `SHUTDOWN` | System shutdown | Returns to home position and powers off |

**Transitions:**

| From | To | Trigger |
|------|-----|---------|
| `IDLE` | `TRACKING` | DOA angle detected with confidence above threshold |
| `IDLE` | `VOICE` | Voice wake word or button press |
| `TRACKING` | `IDLE` | Sound source lost for timeout period |
| `TRACKING` | `VOICE` | Voice command detected during tracking |
| `VOICE` | `WAVING` | LLM parses "wave" intent |
| `VOICE` | `DANCING` | LLM parses "dance" intent |
| `VOICE` | `TRACKING` | LLM parses "track" intent |
| `VOICE` | `IDLE` | Command execution complete |
| `WAVING` | `IDLE` | Animation complete |
| `DANCING` | `IDLE` | Animation complete |
| `*` | `SHUTDOWN` | SIGINT/SIGTERM or "shutdown" voice command |

**中文**

系统以有限状态机运行，具有以下状态和转换：

```
                    +-----------+
           +------->|   空闲    |<--------+
           |        | (呼吸动画) |         |
           |        +----+------+         |
           |             |                |
           |  语音指令   |  检测到 DOA    |
           |             v                |
           |        +----+------+         |
           |        |   追踪    |         |
           |        | (跟随)    |         |
           |        +----+------+         |
           |             |                |
           |   语音指令  |  挥手指令      |
           |             v                |
           |        +----+------+         |
           |   +--->|   挥手    |         |
           |   |    | (挥手)    |         |
           |   |    +----+------+         |
           |   |         |                |
           |   | 跳舞指令 |  超时          |
           |   |         v                |
           |   |    +----+------+         |
           |   +--->|   跳舞    |         |
           |        | (跳舞)    |---------+
           |        +----+------+
           |             |
           |   关机指令   |
           v             v
      +-----------------------+
      |         关机          |
      |    (清理并退出)       |
      +-----------------------+
```

**状态说明：**

| 状态 | 说明 | 机械臂行为 |
|------|------|-----------|
| `空闲` | 系统待机 | 呼吸动画（缓慢周期性运动） |
| `追踪` | DOA 追踪模式 | 机械臂跟随声源方向 |
| `挥手` | 挥手动画 | 执行预设挥手动作 |
| `跳舞` | 跳舞动画 | 执行预设跳舞序列 |
| `语音` | 语音指令处理 | 执行 LLM 解析的指令 |
| `关机` | 系统关机 | 返回原位并断电 |

---

## 5. Safety Design / 安全设计

**English**

Safety is a critical aspect of the robotic control system. The following safety mechanisms are implemented:

### 5.1 Joint Limit Protection / 关节限位保护

```python
# URDF-compliant joint limits (example)
JOINT_LIMITS = {
    'base':     (-180, 180),   # degrees
    'shoulder': (-90, 90),
    'elbow':    (-120, 120),
    'wrist1':   (-90, 90),
    'wrist2':   (-90, 90),
    'gripper':  (0, 60),
}
```

- All target angles are clamped to URDF-defined limits before execution
- Software limits are stricter than hardware limits to provide safety margin

### 5.2 Motion Interpolation / 运动插值

- All joint movements use smooth interpolation (e.g., linear or cosine ease)
- Sudden jumps in position are prevented
- Configurable interpolation speed and acceleration profiles

### 5.3 Cooldown System / 冷却系统

- Each joint maintains a cooldown timer after movement
- Rapid successive commands to the same joint are queued or dropped
- Prevents servo motor overheating and mechanical wear

### 5.4 Anti-Jitter Filtering / 防抖过滤

- DOA angle inputs are filtered using moving average or hysteresis
- Small fluctuations (< threshold) in DOA are ignored
- Prevents erratic arm movements from noisy audio input

### 5.5 Emergency Stop / 紧急停止

- SIGINT (Ctrl+C) triggers immediate graceful shutdown
- All servos return to home position before power-off
- Configurable emergency stop button (GPIO)

**中文**

安全是机器人控制系统的关键方面。已实现以下安全机制：

### 5.1 关节限位保护

所有目标角度在执行前均被钳制到 URDF 定义的限位。软件限位比硬件限位更严格，以提供安全余量。

### 5.2 运动插值

- 所有关节运动使用平滑插值（线性或余弦缓动）
- 防止位置突变
- 可配置的插值速度和加速度曲线

### 5.3 冷却系统

- 每个关节在运动后维护冷却计时器
- 对同一关节的快速连续指令将被排队或丢弃
- 防止伺服电机过热和机械磨损

### 5.4 防抖过滤

- DOA 角度输入使用移动平均或迟滞进行过滤
- 忽略 DOA 的小幅波动（< 阈值）
- 防止嘈杂音频输入导致机械臂不稳定运动

### 5.5 紧急停止

- SIGINT (Ctrl+C) 触发立即优雅关机
- 断电前所有伺服返回原位
- 可配置紧急停止按钮 (GPIO)

---

## 6. Extension Guide / 扩展指南

### 6.1 How to Add a New Action / 如何添加新动作

**English**

To add a new action (e.g., "salute", "stretch"):

1. **Define the action function** in `ArmCtrl` module:

```python
# In arm_controller.py

def action_salute(self):
    """Execute salute gesture."""
    # Define keyframes: [(joint_angles, duration), ...]
    keyframes = [
        ([0, -30, 90, 0, 0, 30], 1.0),    # Raise hand
        ([0, -30, 90, 0, 0, 30], 1.5),    # Hold
        ([0, 0, 0, 0, 0, 0], 1.0),         # Return
    ]
    self.play_animation(keyframes)
```

2. **Register the action** in the command dispatcher:

```python
# In sys_main.py

self.actions = {
    'wave': self.arm.action_wave,
    'dance': self.arm.action_dance,
    'salute': self.arm.action_salute,  # Add here
}
```

3. **Update the LLM prompt** to include the new action:

```python
# In voice_assistant.py

SYSTEM_PROMPT = """
Available actions:
- wave: Wave hand greeting
- dance: Perform dance routine
- salute: Salute gesture  # Add here
- track: Start DOA tracking
- stop: Return to idle
"""
```

**中文**

添加新动作（例如 "敬礼"、"伸展"）：

1. 在 `ArmCtrl` 模块中**定义动作函数**
2. 在指令调度器中**注册动作**
3. **更新 LLM 提示词**以包含新动作

### 6.2 How to Add a New Mode / 如何添加新模式

**English**

To add a new operating mode (e.g., "Gesture Control"):

1. **Define the mode handler** in `SysMain`:

```python
# In sys_main.py

class Mode:
    TRACKING = 'tracking'
    VOICE = 'voice'
    GESTURE = 'gesture'  # New mode

class SysMain:
    def run_gesture_mode(self):
        """Gesture control mode loop."""
        while self.current_mode == Mode.GESTURE:
            gesture = self.respeaker.detect_gesture()
            if gesture:
                self.arm.execute_gesture(gesture)
            time.sleep(0.05)
```

2. **Add mode transition logic**:

```python
# In state machine

def transition(self, event):
    if event == 'gesture_command':
        self.set_mode(Mode.GESTURE)
    # ...
```

3. **Register mode switching command**:

```python
# In voice assistant prompt

"""
Mode switching commands:
- "switch to tracking" -> tracking mode
- "switch to voice" -> voice command mode
- "switch to gesture" -> gesture mode  # Add here
"""
```

**中文**

添加新的运行模式（例如 "手势控制"）：

1. 在 `SysMain` 中**定义模式处理器**
2. **添加模式转换逻辑**
3. **注册模式切换指令**

---

## 7. File Structure / 文件结构

```
reBot-Arm-reSpeaker-Flex/
├── LICENSE                     # MIT License
├── CHANGELOG.md                # Version history
├── .gitignore                  # Git ignore rules
├── README.md                   # Project documentation
├── environment.yml             # Conda environment
├── docs/
│   └── ARCHITECTURE.md         # This document
├── sound_tracking_arm.py       # Main program entry point
├── modules/
│   ├── __init__.py
│   ├── arm_controller.py       # ArmCtrl module
│   ├── voice_assistant.py      # VoiceAsst module
│   ├── respeaker_driver.py     # ReSpeaker module
│   └── sys_main.py             # SysMain module
└── config/
    ├── arm_config.yaml         # Arm joint limits & calibration
    └── prompts.yaml            # LLM system prompts
```

---

## 8. API Reference / API 参考

### Environment Variables / 环境变量

| Variable / 变量 | Required / 必需 | Description / 说明 |
|----------------|----------------|-------------------|
| `GROQ_API_KEY` | Yes / 是 | Groq API key for STT and LLM |
| `ARM_SERIAL_PORT` | No / 否 | Serial port for arm (default: `/dev/ttyUSB0`) |
| `RESPEAKER_INDEX` | No / 否 | Audio device index for reSpeaker |
| `TTS_VOICE` | No / 否 | Edge-TTS voice (default: `en-US-AriaNeural`) |
| `LOG_LEVEL` | No / 否 | Logging level (default: `INFO`) |

---

*End of Document / 文档结束*
