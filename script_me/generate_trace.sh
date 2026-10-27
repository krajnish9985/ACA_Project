export PIN_ROOT=/workspace/pin
mkdir -p /workspace/traces
rm -f /tmp/t.fifo && mkfifo /tmp/t.fifo


xz -T0 -3 < /tmp/t.fifo > /workspace/traces/qwen_p7_n12_trace1.xz &


setarch x86_64 -R $PIN_ROOT/pin \
  -t champsim-upstream/tracer/pin/obj-intel64/champsim_tracer.so \
  -o /tmp/t.fifo -t 4000000000 \
  -start_symbol roi_begin -stop_symbol roi_end -- \
  /workspace/llama.cpp/build/bin/llama-roi \
  -m /workspace/model/qwen2.5-0.5b-instruct-fp16.gguf \
  -n 12 "what is life?"


wait
rm /tmp/t.fifo
ls -lh /workspace/traces/