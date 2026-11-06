#!/usr/bin/env bash
# Read-only diagnostics. Never print environment variables, command arguments,
# container mounts, IP addresses, tokens or application request logs.
set -u
if [[ "$(uname -s)" != Linux ]]; then
    echo 'Zaženi na Raspberry Pi (Linux).'
    exit 1
fi
printf 'TIME UTC: '; date -u '+%F %T'
printf 'MODEL: '; tr -d '\0' </proc/device-tree/model 2>/dev/null || true
printf '\nKERNEL: '; uname -srmo
printf '\nMEMORY (MiB)\n'; free -m
printf '\nFILESYSTEM\n'; df -hT / .
printf '\nPRESSURE\n'
for resource in cpu memory io; do
    if [[ -r /proc/pressure/$resource ]]; then
        printf '%s: ' "$resource"; cat "/proc/pressure/$resource"
    fi
done
printf '\nVMSTAT (first row since boot; next rows 1-second samples)\n'
vmstat 1 6
for sample in 1 2 3; do
    printf '\nSAMPLE %s UTC ' "$sample"; date -u '+%T'
    for zone in /sys/class/thermal/thermal_zone*; do
        [[ -r "$zone/temp" ]] || continue
        printf 'temperature %s: ' "$(cat "$zone/type")"
        awk '{printf "%.1f C\n", $1/1000}' "$zone/temp"
    done
    if command -v vcgencmd >/dev/null; then
        vcgencmd get_throttled
        vcgencmd measure_clock arm
    fi
    if command -v docker >/dev/null; then
        mapfile -t containers < <(docker ps --filter name=marinkino --format '{{.Names}}')
        if ((${#containers[@]})); then
            docker stats --no-stream --format 'table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.MemPerc}}\t{{.BlockIO}}\t{{.PIDs}}' "${containers[@]}"
            docker inspect --format '{{.Name}} OOM={{.State.OOMKilled}} restarts={{.RestartCount}} memory_limit={{.HostConfig.Memory}}' "${containers[@]}"
        fi
    fi
    printf 'TOP PROCESSES (names only, no arguments)\n'
    ps -eo comm,rss,%cpu --sort=-rss | head -12
    [[ "$sample" == 3 ]] || sleep 5
done
printf '\nRECENT KERNEL OOM EVENTS (count only)\n'
journalctl -k --since '24 hours ago' --no-pager -q 2>/dev/null |
    awk '/Out of memory|oom-kill|Killed process/{n++} END{print n+0}'
