#!/usr/bin/env bash
set -e
source ./nftables.sh
work=$(mktemp -d)
trap 'rm -r "$work"' EXIT
CONF_DIR="$work"
CONF_FILE="$work/port-forward.conf"
DOMAIN_MAP="$work/domain-targets.json"
BACKUP_DIR="$work"
mkdir "$work/bin"
cat > "$work/bin/getent" <<'MOCK'
#!/usr/bin/env bash
if [[ "$2" == example.com ]]; then
    printf '203.0.113.10 STREAM example.com\n'
else
    exit 2
fi
MOCK
chmod +x "$work/bin/getent"
export PATH="$work/bin:$PATH"
nft() { return 0; }
get_local_ip() { echo 10.0.0.1; }
init_conf() { [[ -f "$CONF_FILE" ]] || write_conf_file; }
enable_ip_forward() { :; }
check_port_conflict() { return 0; }
backup_conf() { :; }
log_action() { :; }
firewall_open_port() { :; }
firewall_close_port() { :; }
domain_requirements() { :; }
setup_domain_timer() { echo setup >> "$work/timer"; }
reload_rules() { return 0; }

do_add <<'INPUT'
17000
example.com
17000
y
INPUT
[[ $(domain_control get 17000) == example.com ]]
[[ $(do_list) == *'203.0.113.10:17000 (example.com)'* ]]
[[ $(cat "$work/timer") == setup ]]
# Change the listening port and keep the domain and target port.
do_edit <<'INPUT'
1
17001


y
INPUT
[[ -z $(domain_control get 17000) ]]
[[ $(domain_control get 17001) == example.com ]]
[[ $(do_list) == *'203.0.113.10:17000 (example.com)'* ]]
grep -q 'tcp dport 17001 dnat to 203\.0\.113\.10:17000$' "$CONF_FILE"
grep -q 'udp dport 17001 dnat to 203\.0\.113\.10:17000$' "$CONF_FILE"
if grep -q 'dport 17000 dnat' "$CONF_FILE"; then exit 1; fi
# Choosing an IPv4 removes the old binding, avoiding later DNS overwrite.
do_edit <<'INPUT'
1

203.0.113.25
18000
y
INPUT
[[ -z $(domain_control get 17001) ]]
[[ $(do_list) == *'203.0.113.25:18000'* ]]
# Rebind at the new listening port.
do_edit <<'INPUT'
1

example.com

y
INPUT
[[ $(domain_control get 17001) == example.com ]]
# When a subsequent move fails, the old config and its domain key must survive.
cp "$CONF_FILE" "$work/before.conf"
cp "$DOMAIN_MAP" "$work/before.json"
reload_rules() { return 1; }
do_edit <<'INPUT'
1
17002


y
INPUT
cmp -s "$CONF_FILE" "$work/before.conf"
cmp -s "$DOMAIN_MAP" "$work/before.json"
reload_rules() { return 0; }
# Delete, with no stale domain mapping left behind.
do_delete <<'INPUT'
1
y
INPUT
[[ -z $(domain_control get 17001) ]]
echo 'domain add/list/edit/rollback/delete: OK'
