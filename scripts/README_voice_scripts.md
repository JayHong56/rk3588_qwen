启动 / 检查 / 停止 sherpa TTS：

./00_start_sherpa_tts.sh
./07_check_voice_stack.sh
./08_stop_sherpa_tts.sh

不录音，直接边生成边播：

./01_chat_no_record.sh \
"<image>请详细描述这张图片，分成5句话，每句话不超过25个字。"

录音 + 生成时间轴：

./02_chat_record_timeline.sh \
"<image>请详细描述这张图片，分成5句话，每句话不超过25个字。"

实时看系统输出音量：

./06_monitor_output_volume.sh