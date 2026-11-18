#!/usr/bin/env bash
set -eu
source ./nftables.sh
work=$(mktemp -d)
trap 'rm -r "$work"' EXIT
CONF_DIR="$work"
CONF_FILE="$work/port-forward.conf"
DOMAIN_MAP="$work/domain-targets.json"
printf 'old config\n' > "$CONF_FILE"
nft() { return 0; }
load_rules() { RULES=("1000|1.1.1.1|443" "1001|1.1.1.1|443"); }
do_list() { :; }
backup_conf() { :; }
write_conf_file() { printf '%s\n' "${RULES[@]}" > "$CONF_FILE"; }
check_port_conflict() { [[ "$1" != 1003 ]]; }
firewall_close_port() { printf 'close %s %s %s\n' "$1" "$2" "$3" >> "$work/firewall"; }
firewall_open_port() { printf 'open %s %s %s\n' "$1" "$2" "$3" >> "$work/firewall"; }
log_action() { :; }
reload_rules() { return 0; }
do_edit <<'INPUT'
1

2.2.2.2
8443
y
INPUT
[[ $(sed -n 1p "$CONF_FILE") == '1000|2.2.2.2|8443' ]]
[[ $(sed -n 2p "$CONF_FILE") == '1001|1.1.1.1|443' ]]
[[ $(sed -n 1p "$work/firewall") == 'close 1000 1.1.1.1 443' ]]
[[ $(sed -n 2p "$work/firewall") == 'open 1000 2.2.2.2 8443' ]]

# Declining an occupied port cancels before any configuration or firewall changes.
cp "$CONF_FILE" "$work/before.conf"
do_edit <<'INPUT'
1
1003
INPUT
cmp -s "$CONF_FILE" "$work/before.conf"
[[ $(wc -l < "$work/firewall" | tr -d ' ') == 2 ]]

# A duplicate forwarding port is rejected; a different port moves the rule.
do_edit <<'INPUT'
1
65536
1001
1002


y
INPUT
[[ $(sed -n 1p "$CONF_FILE") == '1002|1.1.1.1|443' ]]
[[ $(sed -n 2p "$CONF_FILE") == '1001|1.1.1.1|443' ]]
[[ $(sed -n 3p "$work/firewall") == 'open 1002 1.1.1.1 443' ]]
[[ $(sed -n 4p "$work/firewall") == 'close 1000 1.1.1.1 443' ]]
[[ ! -e "$DOMAIN_MAP" ]]

printf 'old config\n' > "$CONF_FILE"
reload_rules() { return 1; }
do_edit <<'INPUT'
1
1002
2.2.2.2
8443
y
INPUT
[[ $(cat "$CONF_FILE") == 'old config' ]]
[[ $(wc -l < "$work/firewall" | tr -d ' ') == 4 ]]
echo 'edit, listening port checks and failed-load rollback: OK'
