# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Planned
- Multi-language voice command support
- Web-based configuration interface
- Remote monitoring dashboard

---

## [1.0.0] - 2025-05-20

### Added
- Initial release with full feature set
- **DOA Sound Source Tracking mode** — real-time Direction of Arrival detection using reSpeaker Flex 4-mic array, driving robotic arm to track sound sources
- **Voice Command Control mode** — natural language control via Groq STT (Whisper) and LLM (Llama) APIs
- **Edge-TTS voice synthesis** — local text-to-speech feedback with configurable voice and speed
- **6-DOF Robotic Arm motion control** — full joint control for reBot Arm B601-DM with joint limit protection
- **Breathing standby animation** — smooth idle motion to indicate ready state
- **Safety mechanisms**:
  - Motion cooldown system to prevent servo overload
  - Anti-jitter filtering for stable positioning
  - URDF-compliant joint angle limits
  - Graceful shutdown handling
- **Dual-mode switching** — runtime toggle between DOA tracking and voice command modes
- **Signal-based lifecycle management** — clean startup and shutdown via SIGINT/SIGTERM
- **Comprehensive logging** — structured debug/info/warning/error logging throughout

### Security
- API key isolation via environment variables
- No hardcoded credentials in source code

---

## Release Links

- [Unreleased]: https://github.com/yourusername/reBot-Arm-reSpeaker-Flex/compare/v1.0.0...HEAD
- [1.0.0]: https://github.com/yourusername/reBot-Arm-reSpeaker-Flex/releases/tag/v1.0.0
