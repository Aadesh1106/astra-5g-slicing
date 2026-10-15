# shared helpers (source me)
# hexec <host> <cmd...>  : run a command inside a Mininet host's namespace
hexec() {
  local h=$1; shift
  local pid
  pid=$(pgrep -f "mininet:$h\$" | head -1)
  sudo mnexec -a "$pid" "$@"
}
of() { sudo ovs-ofctl -O OpenFlow13 "$@"; }
