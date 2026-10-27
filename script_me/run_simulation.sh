
mkdir -p results

#1 token for warmup and 5 tokens for simulation, total 1.695B, well within the trace.
#W=290000000
#S=1405000000 

#2 token for warmup asnd 8 tokens for simulation, total 2.54B, still inside the trace.
W=580000000
S=2248000000
TRACE=./traces/qwen_p7_n12_trace1.xz

for p in lru srrip hawkeye mockingjay; do
    case $p in
        lru)
            BIN=./bin/hashed_perceptron-no-no-no-no-no-no-no-lru-lru-lru-lru-lru-lru-lru-lru-1core-lru
            ;;
        srrip)
            BIN=./bin/hashed_perceptron-no-no-no-no-no-no-no-lru-lru-lru-lru-srrip-lru-lru-lru-1core-srrip
            ;;
        hawkeye)
            BIN=./bin/hashed_perceptron-no-no-no-no-no-no-no-lru-lru-lru-lru-hawkeye-lru-lru-lru-1core-hawkeye
            ;;
        mockingjay)
            BIN=./bin/hashed_perceptron-no-no-no-no-no-no-no-lru-lru-lru-lru-mockingjay-lru-lru-lru-1core-mockingjay
            ;;
    esac

    nohup "$BIN" \
        -warmup_instructions "$W" \
        -simulation_instructions "$S" \
        -traces "$TRACE" \
        > "results/$p.txt" 2>&1 &

    echo "Started $p (PID: $!)"
done